/* SPDX-License-Identifier: GPL-2.0-or-later
 * CRT math adapted from zfast_crt_standard, Copyright (C) 2017
 * Greg Hogan (SoltanGris42). Original source and revision: android/shaders/.
 * Hypcade modifications (2026-11-09): GLES2 interface, direct planar YUV
 * sampling/conversion, mild fixed parameters and output-pixel scanline/mask placement.
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
uniform sampler2D planeY;
uniform sampler2D planeU;
uniform sampler2D planeV;
uniform vec2 sourceSize;
// Origin and Y direction in the scaled video rectangle, in output pixels.
uniform vec3 outputGrid;
uniform vec3 yuvOffset;
uniform mat3 yuvMatrix;
void main() {
    vec2 p = uv * sourceSize;
    vec2 i = floor(p) + 0.5;
    vec2 f = p - i;
    p = (i + 4.0*f*f*f) / sourceSize;
    p.x = mix(p.x, uv.x, 0.30);
    vec3 yuv = vec3(texture2D(planeY, p).r,
                    texture2D(planeU, p).r, texture2D(planeV, p).r);
    vec3 colour = clamp(yuvMatrix * (yuv + yuvOffset), 0.0, 1.0);
    // The image has already been sampled at this output pixel. Apply the CRT
    // pattern in display pixels: one dark row every two rows, independent of
    // source resolution, cropping or up/downscaling. No later video resampling.
    vec2 pixel = vec2(gl_FragCoord.x - outputGrid.x,
                     (gl_FragCoord.y - outputGrid.y) * outputGrid.z);
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
