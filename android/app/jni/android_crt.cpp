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
    GLint height = -1;
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
    const GLfloat quad[] = {-1,1,0,0, 1,1,1,0, -1,-1,0,1, 1,-1,1,1};
    GLint previousBuffer;
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &previousBuffer);
    glBindBuffer(GL_ARRAY_BUFFER, shader.vertices);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, previousBuffer);
    glUseProgram(program);
    glUniform1i(glGetUniformLocation(program, "frame"), 0);
    shader.height = glGetUniformLocation(program, "outputHeight");
    LOGI << "Android CRT: zfast-crt initialized (game-layer output-pixel pass, native text and moves, GLES2)";
    return true;
}

bool unavailable() {
    if (!shader.reported) {
        LOGW << "Android CRT unavailable; rendering without scanlines";
        shader.reported = true;
    }
    return false;
}
} // namespace

bool android_crt_available(SDL_Renderer *renderer) {
    const char *name = renderer ? SDL_GetRendererName(renderer) : nullptr;
    if (!name || std::strcmp(name, "opengles2") != 0) return unavailable();
    if (shader.attempted) return shader.program != 0;
    return (SDL_FlushRenderer(renderer) && initialize()) || unavailable();
}

void android_crt_reset(SDL_Renderer *renderer) {
    if (renderer && shader.program && SDL_FlushRenderer(renderer)) {
        glDeleteBuffers(1, &shader.vertices);
        glDeleteProgram(shader.program);
    }
    shader = Shader{};
}

bool android_crt_present(SDL_Renderer *renderer, SDL_Texture *frame) {
    if (!frame || SDL_GetRenderTarget(renderer) || !android_crt_available(renderer)) return false;
    const SDL_PropertiesID props = SDL_GetTextureProperties(frame);
    const GLuint texture = static_cast<GLuint>(SDL_GetNumberProperty(props, SDL_PROP_TEXTURE_OPENGLES2_TEXTURE_NUMBER, 0));
    if (!texture || SDL_GetNumberProperty(props, SDL_PROP_TEXTURE_FORMAT_NUMBER, 0) != SDL_PIXELFORMAT_RGBA32)
        return false;
    float width, height, sx, sy;
    int outputWidth, outputHeight;
    SDL_GetRenderScale(renderer, &sx, &sy);
    if (sx != 1.0f || sy != 1.0f || SDL_RenderViewportSet(renderer) ||
        !SDL_GetTextureSize(frame, &width, &height) ||
        !SDL_GetCurrentRenderOutputSize(renderer, &outputWidth, &outputHeight) ||
        width != outputWidth || height != outputHeight || !SDL_FlushRenderer(renderer)) return false;
    // SDL's target projection stores its logical top at texture v=0. Present it
    // without resizing; the output-pixel CRT pattern cannot be resampled later.
    glViewport(0, 0, outputWidth, outputHeight);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_BLEND);
    glUseProgram(shader.program);
    glUniform1f(shader.height, height);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, texture);
    GLint enabled[2];
    for (int i = 0; i < 2; ++i) {
        glGetVertexAttribiv(i, GL_VERTEX_ATTRIB_ARRAY_ENABLED, &enabled[i]);
        glEnableVertexAttribArray(i);
    }
    GLint previousBuffer;
    glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &previousBuffer);
    glBindBuffer(GL_ARRAY_BUFFER, shader.vertices);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4*sizeof(float), nullptr);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4*sizeof(float), reinterpret_cast<void *>(2*sizeof(float)));
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glBindBuffer(GL_ARRAY_BUFFER, previousBuffer);
    for (int i = 0; i < 2; ++i) if (!enabled[i]) glDisableVertexAttribArray(i);
    return true;
}
