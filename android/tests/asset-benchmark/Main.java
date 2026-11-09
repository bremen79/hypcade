/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypcade.assetbench;
import android.app.Activity;
import android.os.Bundle;
import android.content.res.AssetManager;
import android.util.Log;
import android.widget.TextView;
import java.io.*;
import java.util.*;
public final class Main extends Activity {
    static { System.loadLibrary("assetbench"); }
    static native String run(AssetManager manager,String root,String[] paths);
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView text=new TextView(this);text.setText("Asset benchmark running…");setContentView(text);
        new Thread(()->{
            try {
                ArrayList<String> paths=new ArrayList<>();
                try(BufferedReader reader=new BufferedReader(new InputStreamReader(getAssets().open("asset-list.txt"),"UTF-8"))) {
                    String line;while((line=reader.readLine())!=null) paths.add(line);
                }
                long start=System.nanoTime();
                byte[] buffer=new byte[65536];
                for(String name:paths) {
                    File f=new File(getFilesDir(),name);f.getParentFile().mkdirs();
                    try(InputStream in=getAssets().open(name);FileOutputStream out=new FileOutputStream(f)) {
                        int n;while((n=in.read(buffer))!=-1) out.write(buffer,0,n);
                        out.getFD().sync();
                    }
                }
                Log.i("AssetBench","Extraction with per-file fsync ms="+(System.nanoTime()-start)/1e6);
                String result=run(getAssets(),getFilesDir().getAbsolutePath(),paths.toArray(new String[0]));
                try(FileOutputStream out=new FileOutputStream(new File(getFilesDir(),"results.csv"))) {out.write(result.getBytes("UTF-8"));}
                Log.i("AssetBench",result.startsWith("ERROR")?result:"PASS results.csv");
                runOnUiThread(()->text.setText("Benchmark complete"));
            } catch(Exception e) {Log.e("AssetBench","FAIL",e);}
        },"AssetBench").start();
    }
}
