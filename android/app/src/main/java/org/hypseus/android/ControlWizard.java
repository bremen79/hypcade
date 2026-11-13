/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.widget.Toast;

/** Captures a temporary mapping, commits only after an explicit Save. */
final class ControlWizard {
    private final Activity activity;
    private final Runnable saved;
    private final ControlMap draft=new ControlMap();
    private AlertDialog dialog;
    private int step;
    private ControlMap.Binding pending;
    private long pressed, armed;
    private final ControllerNavigation navigation=new ControllerNavigation();
    private ArcadeInput preview;
    private boolean routing;
    private static final int[] AXES={MotionEvent.AXIS_HAT_X,MotionEvent.AXIS_HAT_Y,MotionEvent.AXIS_X,MotionEvent.AXIS_Y,
        MotionEvent.AXIS_LTRIGGER,MotionEvent.AXIS_RTRIGGER,MotionEvent.AXIS_BRAKE,MotionEvent.AXIS_GAS};
    ControlWizard(Activity activity,Runnable saved) {this.activity=activity;this.saved=saved;}
    void show() {
        dialog=new AlertDialog.Builder(activity).setTitle("Controller for all games").setMessage("")
            .setNegativeButton("Cancel",null).setNeutralButton("Back",null).setPositiveButton("Skip",null).create();
        dialog.setOnKeyListener((d,code,event)->key(event));
        dialog.setOnDismissListener(d->navigation.reset());
        dialog.setOnShowListener(d->{
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->{if(step>0) {step--; draft.bindings.removeIf(b->b.action>=step); pending=null; update();}});
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
                if(step==ControlMap.NAMES.length) save();
                else if(ControlMap.optional(step)) {draft.bindings.removeIf(b->b.action==step);step++;update();}
            });
            dialog.getWindow().getDecorView().setOnGenericMotionListener((v,event)->motion(event));
            update();
        });
        dialog.show();
    }
    private void update() {
        pending=null;armed=SystemClock.uptimeMillis()+200;
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setEnabled(step>0);
        if(step==ControlMap.NAMES.length) {
            StringBuilder summary=new StringBuilder("This mapping applies to every game. Action 1 or Start selects Save; Android Back cancels.\n\n");
            for(ControlMap.Binding b:draft.bindings) summary.append(ControlMap.NAMES[b.action]).append(": ")
                .append(b.axis>=0 ? "axis "+b.axis+(b.sign<0 ? " −" : " +") : KeyEvent.keyCodeToString(b.key)).append('\n');
            dialog.setMessage(summary);dialog.getButton(AlertDialog.BUTTON_POSITIVE).setText("Save");
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).requestFocusFromTouch();
            preview=new ArcadeInput(draft);
        } else {
            dialog.setMessage("Step "+(step+1)+" / "+ControlMap.NAMES.length+"\n\nPress and release: "+ControlMap.NAMES[step]
                +"\n\nUse a keyboard encoder, D-pad, joystick or controller button. Return the stick to centre after each direction."
                +(ControlMap.optional(step) ? "\nOptional: hold an input for 2 seconds, then release to skip." : "\nThis control is required.")
                +"\nAndroid Back cancels. Nothing changes until Save.");
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setText("Skip");
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(ControlMap.optional(step));
        }
    }
    private void save() {
        // Explicit Save must report failure and finish writing before confirming.
        if (!new SetupSettings(activity).saveControls(draft)) {
            Toast.makeText(activity,"Controls could not be saved. Free a little internal storage and try again.",Toast.LENGTH_LONG).show();
            return;
        }
        dialog.dismiss();saved.run();
    }
    private void finishInput() {
        ControlMap.Binding value=pending; pending=null;
        if(ControlMap.optional(step) && SystemClock.uptimeMillis()-pressed>=1800) draft.bindings.removeIf(b->b.action==step);
        else if(!draft.add(value)) {
            Toast.makeText(activity,"That input is already assigned. Use a different button.",Toast.LENGTH_LONG).show();return;
        }
        step++;update();
    }
    private void navigate(int code,boolean down) {
        navigation.mapped(code,down,event->{routing=true;try{return ControllerNavigation.dispatchFocus(dialog.getWindow().getDecorView(),event,dialog::dispatchKeyEvent);}finally{routing=false;}});
    }
    private boolean key(KeyEvent event) {
        if(routing || event.getKeyCode()==KeyEvent.KEYCODE_BACK) return false;
        if(step==ControlMap.NAMES.length) {
            if(preview.key(event,this::navigate)) return true;
            return navigation.key(event,e->{routing=true;try{return ControllerNavigation.dispatchFocus(dialog.getWindow().getDecorView(),e,dialog::dispatchKeyEvent);}finally{routing=false;}});
        }
        if(event.getKeyCode()==KeyEvent.KEYCODE_VOLUME_UP || event.getKeyCode()==KeyEvent.KEYCODE_VOLUME_DOWN) return false;
        if(event.getAction()==KeyEvent.ACTION_DOWN && event.getRepeatCount()==0 && pending==null && SystemClock.uptimeMillis()>=armed) {
            pending=new ControlMap.Binding(step,ArcadeInput.descriptor(event.getDeviceId()),event.getKeyCode(),event.getScanCode(),-1,0);
            pressed=SystemClock.uptimeMillis();
        } else if(event.getAction()==KeyEvent.ACTION_UP && pending!=null && pending.axis<0
                && pending.device.equals(ArcadeInput.descriptor(event.getDeviceId())) && pending.keyMatches(event.getKeyCode(),event.getScanCode())) finishInput();
        return true;
    }
    private boolean motion(MotionEvent event) {
        if(!event.isFromSource(InputDevice.SOURCE_JOYSTICK)) return false;
        if(step==ControlMap.NAMES.length) return preview.motion(event,this::navigate);
        String device=ArcadeInput.descriptor(event.getDeviceId());
        for(int sample=0;sample<=event.getHistorySize() && step<ControlMap.NAMES.length;sample++) {
            if(pending!=null) {
                float value=pending.axis<0 ? 0 : sample<event.getHistorySize()
                        ? event.getHistoricalAxisValue(pending.axis,sample) : event.getAxisValue(pending.axis);
                if(pending.axis>=0 && pending.device.equals(device) && value*pending.sign<.35f) finishInput();
            } else if(SystemClock.uptimeMillis()>=armed) {
                for(int axis:AXES) {
                    float value=sample<event.getHistorySize() ? event.getHistoricalAxisValue(axis,sample) : event.getAxisValue(axis);
                    if((axis==MotionEvent.AXIS_LTRIGGER || axis==MotionEvent.AXIS_RTRIGGER || axis==MotionEvent.AXIS_BRAKE || axis==MotionEvent.AXIS_GAS ? value : Math.abs(value))>.65f) {
                        pending=new ControlMap.Binding(step,device,0,0,axis,value<0 ? -1 : 1);
                        pressed=SystemClock.uptimeMillis();break;
                    }
                }
            }
        }
        return true;
    }
}
