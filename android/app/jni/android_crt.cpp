/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#include "android_crt.h"
#include "android_crt_shader.h"
#include <GLES2/gl2.h>
#include <plog/Log.h>
#include <cstring>

namespace {
struct Shader {
    GLuint program = 0, vertices = 0;
    GLint grid = -1, size = -1, offset = -1, matrix = -1;
    bool attempted = false, reported = false;
} shader;

GLuint compile(GLenum type, const char *source) {
    GLuint id = glCreateShader(type);
    glShaderSource(id, 1, &source, nullptr);
    glCompileShader(id);
    GLint success = 0;
    glGetShaderiv(id, GL_COMPILE_STATUS, &success);
    if (!success) {
        char log[1024] = {};
        glGetShaderInfoLog(id, sizeof(log), nullptr, log);
        LOGW << "Android CRT shader compilation failed: " << log;
        glDeleteShader(id);
        return 0;
    }
    return id;
}

bool initialize() {
    if (shader.attempted) return shader.program != 0;
    shader.attempted = true;
    GLuint vertex = compile(GL_VERTEX_SHADER, crt_vertex_shader);
    GLuint fragment = compile(GL_FRAGMENT_SHADER, crt_fragment_shader);
    GLuint program = 0;
    if (vertex && fragment) {
        program = glCreateProgram();
        glAttachShader(program, vertex);
        glAttachShader(program, fragment);
        glBindAttribLocation(program, 0, "position");
        glBindAttribLocation(program, 1, "texcoord");
        glLinkProgram(program);
        GLint linked = 0;
        glGetProgramiv(program, GL_LINK_STATUS, &linked);
        if (!linked) {
            char log[1024] = {};
            glGetProgramInfoLog(program, sizeof(log), nullptr, log);
            LOGW << "Android CRT shader link failed: " << log;
            glDeleteProgram(program);
            program = 0;
        }
    }
    glDeleteShader(vertex);
    glDeleteShader(fragment);
    if (!program) return false;
    shader.program = program;
    glGenBuffers(1, &shader.vertices);
    glUseProgram(program);
    glUniform1i(glGetUniformLocation(program, "planeY"), 0);
    glUniform1i(glGetUniformLocation(program, "planeU"), 1);
    glUniform1i(glGetUniformLocation(program, "planeV"), 2);
    shader.size = glGetUniformLocation(program, "sourceSize");
    shader.grid = glGetUniformLocation(program, "outputGrid");
    shader.offset = glGetUniformLocation(program, "yuvOffset");
    shader.matrix = glGetUniformLocation(program, "yuvMatrix");
    LOGI << "Android CRT: zfast-crt initialized (output-pixel scanlines, single-pass YUV, GLES2)";
    return true;
}

bool unavailable() {
    if (!shader.reported) {
        LOGW << "Android CRT unavailable; rendering video without scanlines";
        shader.reported = true;
    }
    return false;
}
} // namespace

void android_crt_reset(SDL_Renderer *renderer) {
    // Flush while SDL's renderer/context is still alive; no decoder-thread GL.
    if (renderer && shader.program && SDL_FlushRenderer(renderer)) {
        glDeleteBuffers(1, &shader.vertices);
        glDeleteProgram(shader.program);
    }
    shader = Shader{};
}

bool android_crt_draw(SDL_Renderer *renderer, SDL_Texture *yuv,
                      const SDL_FRect *source, const SDL_FRect &destination) {
    if (std::strcmp(SDL_GetRendererName(renderer), "opengles2") != 0)
        return unavailable();
    const SDL_PropertiesID props = SDL_GetTextureProperties(yuv);
    const GLuint planes[] = {
        static_cast<GLuint>(SDL_GetNumberProperty(props, SDL_PROP_TEXTURE_OPENGLES2_TEXTURE_NUMBER, 0)),
        static_cast<GLuint>(SDL_GetNumberProperty(props, SDL_PROP_TEXTURE_OPENGLES2_TEXTURE_U_NUMBER, 0)),
        static_cast<GLuint>(SDL_GetNumberProperty(props, SDL_PROP_TEXTURE_OPENGLES2_TEXTURE_V_NUMBER, 0))
    };
    if (!planes[0] || !planes[1] || !planes[2]) return unavailable();
    // Match SDL's actual texture colorspace; never silently change video levels.
    const auto colorspace = static_cast<SDL_Colorspace>(
        SDL_GetNumberProperty(props, SDL_PROP_TEXTURE_COLORSPACE_NUMBER, SDL_COLORSPACE_YUV_DEFAULT));
    const bool bt709 = SDL_ISCOLORSPACE_MATRIX_BT709(colorspace);
    if (!bt709 && !SDL_ISCOLORSPACE_MATRIX_BT601(colorspace)) return unavailable();
    const bool limited = SDL_ISCOLORSPACE_LIMITED_RANGE(colorspace);
    const float kr = bt709 ? 0.2126f : 0.299f;
    const float kb = bt709 ? 0.0722f : 0.114f;
    const float kg = 1.0f - kr - kb;
    const float ys = limited ? 255.0f / 219.0f : 1.0f;
    const float cs = limited ? 255.0f / 224.0f : 1.0f;
    const GLfloat matrix[] = {ys, ys, ys, 0, -2*kb*(1-kb)/kg*cs, 2*(1-kb)*cs,
                             2*(1-kr)*cs, -2*kr*(1-kr)/kg*cs, 0};
    float width, height;
    int outputWidth, outputHeight;
    float scaleX, scaleY;
    SDL_GetRenderScale(renderer, &scaleX, &scaleY);
    if (scaleX != 1.0f || scaleY != 1.0f || SDL_RenderViewportSet(renderer)
        || !SDL_GetTextureSize(yuv, &width, &height)
        || !SDL_GetCurrentRenderOutputSize(renderer, &outputWidth, &outputHeight)
        || outputWidth <= 0 || outputHeight <= 0) return unavailable();
    // This public interop API submits pending SDL work and invalidates its GL
    // state cache, so following SDL overlays restore their own drawing state.
    if (!SDL_FlushRenderer(renderer) || !initialize()) return unavailable();
    const SDL_FRect src = source ? *source : SDL_FRect{0, 0, width, height};
    const bool target = SDL_GetRenderTarget(renderer) != nullptr;
    const float left = 2*destination.x/outputWidth - 1;
    const float right = 2*(destination.x+destination.w)/outputWidth - 1;
    const float top = 2*destination.y/outputHeight - 1;
    const float bottom = 2*(destination.y+destination.h)/outputHeight - 1;
    const float flip = target ? 1.0f : -1.0f;
    const float u0 = src.x/width, u1 = (src.x+src.w)/width;
    const float v0 = src.y/height, v1 = (src.y+src.h)/height;
    const GLfloat quad[] = {left,top*flip,u0,v0, right,top*flip,u1,v0,
                           left,bottom*flip,u0,v1, right,bottom*flip,u1,v1};
    glViewport(0, 0, outputWidth, outputHeight);
    if (SDL_RenderClipEnabled(renderer)) {
        SDL_Rect clip;
        SDL_GetRenderClipRect(renderer, &clip);
        glEnable(GL_SCISSOR_TEST);
        glScissor(clip.x, target ? clip.y : outputHeight-clip.y-clip.h, clip.w, clip.h);
    } else glDisable(GL_SCISSOR_TEST);
    glDisable(GL_BLEND);
    glUseProgram(shader.program);
    glUniform2f(shader.size, width, height);
    // SDL render targets and the window have opposite GL Y origins. Both use
    // the final-size video rectangle, including letterboxing/crop offsets.
    glUniform3f(shader.grid, destination.x,
                target ? destination.y : outputHeight - destination.y,
                target ? 1.0f : -1.0f);
    glUniform3f(shader.offset, limited ? -16.0f/255.0f : 0.0f, -128.0f/255.0f, -128.0f/255.0f);
    glUniformMatrix3fv(shader.matrix, 1, GL_FALSE, matrix);
    // Restore texture parameters because SDL also caches these per texture.
    GLint filters[3][2];
    for (int i = 0; i < 3; ++i) {
        glActiveTexture(GL_TEXTURE0 + i);
        glBindTexture(GL_TEXTURE_2D, planes[i]);
        glGetTexParameteriv(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, &filters[i][0]);
        glGetTexParameteriv(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, &filters[i][1]);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    }
    GLint enabled[2];
    for (int i = 0; i < 2; ++i) {
        glGetVertexAttribiv(i, GL_VERTEX_ATTRIB_ARRAY_ENABLED, &enabled[i]);
        glEnableVertexAttribArray(i);
    }
    GLint previousBuffer;
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &previousBuffer);
    glBindBuffer(GL_ARRAY_BUFFER, shader.vertices);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STREAM_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4*sizeof(float), nullptr);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4*sizeof(float), reinterpret_cast<void *>(2*sizeof(float)));
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glBindBuffer(GL_ARRAY_BUFFER, previousBuffer);
    for (int i = 0; i < 2; ++i) if (!enabled[i]) glDisableVertexAttribArray(i);
    for (int i = 0; i < 3; ++i) {
        glActiveTexture(GL_TEXTURE0 + i);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filters[i][0]);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filters[i][1]);
    }
    glActiveTexture(GL_TEXTURE0);
    return true;
}
