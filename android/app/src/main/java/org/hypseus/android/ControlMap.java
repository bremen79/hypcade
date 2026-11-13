/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import android.util.Base64;
import java.util.List;

/** Small, versioned, device-descriptor-based mapping, independent of Android UI. */
final class ControlMap {
    static final String[] NAMES = {"Up", "Down", "Left", "Right", "Action 1", "Action 2", "Action 3", "Coin", "Start", "Pause", "Exit game", "Game options / Service", "Start 2 players"};
    // Android key codes passed through SDL's existing keyboard path.
    static final int[] KEYS = {19,20,21,22,113,57,62,12,8,44,111,16,9};
    boolean canPlay(boolean arcade, boolean touch) {
        return isComplete() || (!arcade && touch);
    }
    static boolean optional(int action) { return action==5 || action==6 || action==9 || action==11 || action==12; }
    static final class Binding {
        final int action, key, scan, axis, sign;
        final String device;
        Binding(int action,String device,int key,int scan,int axis,int sign) {
            this.action=action; this.device=device; this.key=key; this.scan=scan; this.axis=axis; this.sign=sign;
        }
        boolean sameInput(Binding b) {
            return device.equals(b.device) && axis==b.axis && (axis>=0 ? sign==b.sign : scan>0 && b.scan>0 ? scan==b.scan : key==b.key);
        }
        boolean keyMatches(int code,int scanCode) { return axis<0 && (scan>0 && scanCode>0 ? scan==scanCode : key==code); }
    }
    final List<Binding> bindings = new ArrayList<>();
    boolean isComplete() {
        for (int action = 0; action < NAMES.length; ++action) {
            if (optional(action)) continue;
            boolean assigned = false;
            for (Binding binding : bindings) if (binding.action == action) assigned = true;
            if (!assigned) return false;
        }
        return true;
    }
    boolean owns(String device) { for(Binding b:bindings) if(b.device.equals(device)) return true; return false; }
    boolean add(Binding value) {
        for(Binding b:bindings) if(b.action!=value.action && b.sameInput(value)) return false;
        bindings.removeIf(b -> b.action==value.action);
        bindings.add(value); return true;
    }
    String encode() {
        StringBuilder out=new StringBuilder("1\n");
        for(Binding b:bindings) out.append(b.action).append('|').append(Base64.encodeToString(b.device.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP))
            .append('|').append(b.key).append('|').append(b.scan).append('|').append(b.axis).append('|').append(b.sign).append('\n');
        return out.toString();
    }
    static ControlMap decode(String data) {
        ControlMap map=new ControlMap();
        if(data==null || data.length()>16384 || !data.startsWith("1\n")) return map;
        try {
            for(String raw:data.substring(2).split("\n")) {
                String line=raw.trim();
                if(line.isEmpty()) continue;
                String[] v=line.split("\\|",-1);
                if(v.length!=6) return new ControlMap();
                Binding b=new Binding(Integer.parseInt(v[0]),new String(Base64.decode(v[1], Base64.NO_WRAP),StandardCharsets.UTF_8),
                    Integer.parseInt(v[2]),Integer.parseInt(v[3]),Integer.parseInt(v[4]),Integer.parseInt(v[5]));
                if(b.action<0 || b.action>=NAMES.length || b.device.isEmpty() || b.axis < -1 || b.axis>63
                    || b.key<0 || b.scan<0 || (b.axis<0 && b.key==0 && b.scan==0) || (b.axis>=0 && Math.abs(b.sign)!=1) || !map.add(b)) return new ControlMap();
            }
        } catch(IllegalArgumentException invalid) { return new ControlMap(); }
        return map;
    }
}
