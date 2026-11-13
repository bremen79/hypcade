/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
/* SPDX-License-Identifier: GPL-2.0-or-later
 * CRT math adapted from zfast_crt_standard, Copyright (C) 2017
 * Greg Hogan (SoltanGris42). Original source and revision: android/shaders/.
 * Hypcade modifications: GLES2 final-frame interface, mild fixed parameters
 * and output-pixel scanline/mask placement after video and text composition.
 * This program is free software under GPL version 2 or any later version,
 * without any warranty. See android/licenses/libmpeg2-COPYING.txt.
 */
#pragma once

static const char *crt_vertex_shader = R"glsl(
attribute vec2 position;
attribute vec2 texcoord;
varying highp vec2 uv;
void main() {
    gl_Position = vec4(position, 0.0, 1.0);
    uv = texcoord;
}
)glsl";

static const char *crt_fragment_shader = R"glsl(
precision highp float;
varying highp vec2 uv;
uniform sampler2D frame;
uniform float outputHeight;
void main() {
    // Video, native game text and recorded moves are composed at output size.
    // Added score/lives HUD, FPS and cabinet bezels are drawn after this pass.
    vec3 colour = texture2D(frame, uv).rgb;
    vec2 pixel = vec2(gl_FragCoord.x, outputHeight - gl_FragCoord.y);
    float scan = fract(floor(pixel.y) * 0.5 + 0.5) - 0.5;
    float Y = scan*scan;
    float YY = Y*Y;
    float mask = 1.0 - 0.12 * float(fract(floor(pixel.x)*-0.5) < 0.5);
    float scanLineWeight = 1.08 - 2.5*(Y - 2.05*YY);
    float scanLineWeightB = 1.0 - 4.0*(YY - 2.8*YY*Y);
    gl_FragColor = vec4(colour * mix(scanLineWeight*mask, scanLineWeightB,
                                   dot(colour, vec3(0.3333*0.8))), 1.0);
}
)glsl";
