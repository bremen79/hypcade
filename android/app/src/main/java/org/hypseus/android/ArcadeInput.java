/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-3.0-or-later */
package org.hypseus.android;

import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import java.util.HashSet;
import java.util.Set;

/** Own mapped devices before SDL handles them, avoiding duplicate joystick/key events. */
final class ArcadeInput {
    interface Sink { void key(int code, boolean down); }
    final ControlMap map;
    private final Set<ControlMap.Binding> held = new HashSet<>();
    ArcadeInput(ControlMap map) { this.map=map; }
    static String descriptor(int id) {
        InputDevice device=InputDevice.getDevice(id);
        return device==null ? "virtual:"+id : device.getDescriptor();
    }
    private void state(ControlMap.Binding binding,boolean down,Sink sink) {
        boolean changed=down ? held.add(binding) : held.remove(binding);
        if(changed) sink.key(ControlMap.KEYS[binding.action],down);
    }
    boolean key(KeyEvent event,Sink sink) {
        int code=event.getKeyCode();
        // Android's navigation and volume controls remain available for recovery.
        if(code==KeyEvent.KEYCODE_BACK || code==KeyEvent.KEYCODE_VOLUME_UP || code==KeyEvent.KEYCODE_VOLUME_DOWN || code==KeyEvent.KEYCODE_VOLUME_MUTE) return false;
        String device=descriptor(event.getDeviceId());
        if(!map.owns(device)) return false;
        for(ControlMap.Binding b:map.bindings) if(b.device.equals(device) && b.keyMatches(code,event.getScanCode()))
            state(b,event.getAction()==KeyEvent.ACTION_DOWN,sink);
        return true;
    }
    boolean motion(MotionEvent event,Sink sink) {
        if(!event.isFromSource(InputDevice.SOURCE_JOYSTICK)) return false;
        String device=descriptor(event.getDeviceId());
        if(!map.owns(device)) return false;
        // Android batches joystick samples; retain quick press/release transitions.
        for(int sample=0;sample<=event.getHistorySize();sample++) {
            for(ControlMap.Binding b:map.bindings) if(b.device.equals(device) && b.axis>=0) {
                float value=(sample<event.getHistorySize() ? event.getHistoricalAxisValue(b.axis,sample)
                        : event.getAxisValue(b.axis))*b.sign;
                state(b,value>(held.contains(b) ? .35f : .55f),sink);
            }
        }
        return true;
    }
    void release(Sink sink) {
        for(ControlMap.Binding b:new HashSet<>(held)) state(b,false,sink);
    }
}
