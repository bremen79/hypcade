/* Hypcade: Copyright (C) 2026 Francesco Orabona. */
// SPDX-License-Identifier: GPL-3.0-or-later
#include "android_crt.h"
#include "android_ldp1450_text.h"
#include "video_android.h"
#include "../../src/scoreboard/scoreboard_collection.h"
#include <GLES2/gl2.h>
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <vector>

static unsigned testControls = 0;
bool arcade_visual_moves_enabled() { return true; }
unsigned arcade_visual_controls() { return testControls; }
bool arcade_has_calculated_moves(const char *game) {
    return game && (!strcmp(game,"dle21") || !strcmp(game,"ace") || !strcmp(game,"sae") || !strcmp(game,"lair_ita") || !strcmp(game,"laireuro"));
}

constexpr int W = 128, H = 96;
using Pixels = std::vector<unsigned char>;

static Pixels capture(SDL_Renderer *renderer) {
    SDL_Surface *raw = SDL_RenderReadPixels(renderer, nullptr);
    assert(raw);
    SDL_Surface *rgba = SDL_ConvertSurface(raw, SDL_PIXELFORMAT_RGBA32);
    assert(rgba && rgba->w == W && rgba->h == H);
    Pixels pixels(W*H*4);
    for (int y=0;y<H;++y)
        std::copy_n(static_cast<unsigned char *>(rgba->pixels)+y*rgba->pitch, W*4, pixels.data()+y*W*4);
    SDL_DestroySurface(rgba);SDL_DestroySurface(raw);
    return pixels;
}

static SDL_Texture *font(SDL_Renderer *renderer, SDL_PixelFormat format, bool white) {
    Pixels data(8*8*4, 0);
    for (int y=1;y<7;++y)for(int x=2;x<6;++x) {
        unsigned char *p=data.data()+(y*8+x)*4;
        p[0]=white ? 255 : (format==SDL_PIXELFORMAT_BGRA32 ? 25 : 200);
        p[1]=white ? 255 : 80;
        p[2]=white ? 255 : (format==SDL_PIXELFORMAT_BGRA32 ? 200 : 25);
        p[3]=255;
    }
    SDL_Texture *t=SDL_CreateTexture(renderer,format,SDL_TEXTUREACCESS_STATIC,8,8);
    assert(t && SDL_UpdateTexture(t,nullptr,data.data(),8*4));
    assert(SDL_SetTextureBlendMode(t,SDL_BLENDMODE_BLEND));
    assert(SDL_SetTextureScaleMode(t,SDL_SCALEMODE_NEAREST));
    return t;
}

static void check(const Pixels &plain, const Pixels &crt) {
    // Independent scalar reference for every composed pixel, including fonts,
    // transparent overlays, colour modulation and rotation markers.
    for(int y=0;y<H;++y)for(int x=0;x<W;++x) {
        const float scan=(y%2 ? -0.5f : 0.0f);
        const float Y=scan*scan, YY=Y*Y;
        const float mask=x%2 ? 1.0f : 0.88f;
        const float a=(1.08f-2.5f*(Y-2.05f*YY))*mask;
        const float b=1.0f-4.0f*(YY-2.8f*YY*Y);
        int i=(y*W+x)*4;
        float luminance=(plain[i]+plain[i+1]+plain[i+2])/255.0f*0.3333f*0.8f;
        for(int c=0;c<3;++c) {
            const float expected=std::min(255.0f,plain[i+c]*(a+(b-a)*luminance));
            if(std::abs(expected-crt[i+c])>=2.1f) {
                std::fprintf(stderr,"pixel %d,%d c%d plain=%d actual=%d expected=%f\n",x,y,c,plain[i+c],crt[i+c],expected);
                std::abort();
            }
        }
    }
}

static void checkText(SDL_Renderer *r) {
    SDL_Surface *bitmap=SDL_LoadBMP("pics/ldp1450font.bmp");
    assert(bitmap);
    assert(SDL_SetSurfaceColorKey(bitmap,true,SDL_MapSurfaceRGB(bitmap,0,0,0)));
    SDL_Texture *atlas=SDL_CreateTextureFromSurface(r,bitmap);
    assert(atlas && SDL_SetTextureScaleMode(atlas,SDL_SCALEMODE_NEAREST));
    SDL_Surface *legacy=SDL_CreateSurface(W,H,SDL_PIXELFORMAT_RGBA32);
    assert(legacy);
    video::Ldp1450Text line;
    const char *cases[]={"UP", "RIGHT", "BUTTON", "A + B", "0123456789", "\x13", "", "             "};
    for(auto text:cases)for(int x:{2,-4,110}) {
        assert(SDL_ClearSurface(legacy,0,0,0,0));
        int at=x;
        for(const char *s=text;*s;++s,at+=15) {
            unsigned c=static_cast<unsigned char>(*s);
            int glyph=c>=0x26 && c<=0x39 ? c-0x25 : c>='A' && c<='Z' ? c-0x2a : c==0x13 ? 0x32 : 0x31;
            SDL_Rect source={glyph*16,0,16,16},dest={at,22,16,16};
            assert(SDL_FillSurfaceRect(legacy,&dest,0));
            assert(SDL_BlitSurface(bitmap,&source,legacy,&dest));
        }
        SDL_Texture *reference=SDL_CreateTextureFromSurface(r,legacy);
        assert(reference && SDL_SetTextureScaleMode(reference,SDL_SCALEMODE_NEAREST));
        assert(SDL_SetRenderDrawColor(r,126,126,126,255) && SDL_RenderClear(r));
        assert(SDL_RenderTexture(r,reference,nullptr,nullptr));Pixels expected=capture(r);
        line.set(text,x,22);
        for(int repeat=0;repeat<2;++repeat) {
            assert(SDL_RenderClear(r));
            assert(video::draw_singleline_LDP1450(r,atlas,line,{0,0,W,H},{0,0,W,H}));
            Pixels actual=capture(r);
            if(actual!=expected) {
                int differences=0;
                for(size_t i=0;i<actual.size();++i)if(actual[i]!=expected[i])++differences;
                std::fprintf(stderr,"font mismatch backend=%s text=%s x=%d differences=%d\n",SDL_GetRendererName(r),text,x,differences);
                std::abort();
            }
        }
        SDL_DestroyTexture(reference);
    }
    // Bounded input, blank replacement and layout cache invalidation.
    char longText[200];std::fill_n(longText,199,'A');longText[199]=0;
    line.set(longText,0,0);assert(std::strlen(line.text)==127);
    assert(video::draw_singleline_LDP1450(r,atlas,line,{0,0,W,H},{0,0,W,H},true));
    line.set("",0,0);assert(video::draw_singleline_LDP1450(r,atlas,line,{0,0,W,H},{0,0,W,H}));
    SDL_DestroyTexture(atlas);SDL_DestroySurface(bitmap);SDL_DestroySurface(legacy);
    std::printf("Shared LDP1450 GPU text matches legacy bitmap rendering: directions, button, digits, special glyph, spaces, clipping, replacement and cached redraw.\n");
}

static void checkMoveSources(SDL_Renderer *r) {
    using namespace video::android_video;
    SDL_Surface *bitmap=SDL_LoadBMP("pics/ldp1450font.bmp");
    assert(bitmap && SDL_SetSurfaceColorKey(bitmap,true,SDL_MapSurfaceRGB(bitmap,0,0,0)));
    for(const char *game : {"lair2","ace91","dle21","ace","sae","lair_ita","laireuro"}) {
        bool native=std::strcmp(game,"lair2")==0 || std::strcmp(game,"ace91")==0;
        release_renderer(r);assert(init_text(r,bitmap,false,game,native));
        queue_text(2,native ? "SWORD" : "",20,22);
        testControls=0;
        assert(SDL_SetRenderDrawColor(r,126,126,126,255) && SDL_RenderClear(r));
        draw_game_text(r,{0,0,320,240},{0,0,W,H});Pixels reference=capture(r);
        testControls=16;
        assert(SDL_RenderClear(r));draw_game_text(r,{0,0,320,240},{0,0,W,H});
        assert((capture(r)==reference)==native);
    }
    testControls=0;queue_text(2,"",20,22);release_renderer(r);SDL_DestroySurface(bitmap);
    std::printf("Move-source rendering passed on %s: native-only DL2/Ace91, calculated DLE21/Ace.\n",SDL_GetRendererName(r));
}

static void checkBackend(SDL_Renderer *r) {
    using namespace video::android_video;
    SDL_Surface *bitmap=SDL_LoadBMP("pics/ldp1450font.bmp");
    assert(bitmap && SDL_SetSurfaceColorKey(bitmap,true,SDL_MapSurfaceRGB(bitmap,0,0,0)));
    assert(init_text(r,bitmap,false,"lair2",true));
    SDL_Rect output={0,0,W,H};
    SDL_Texture *target=game_target(r,output,true,false);
    assert(target && game_target(r,output,true,false)==target);
    assert(SDL_SetRenderTarget(r,target));
    assert(SDL_SetRenderDrawColor(r,126,126,126,255) && SDL_RenderClear(r));
    { std::lock_guard<std::recursive_mutex> lock(video::android_video::mutex());queue_text(2,"SWORD",20,22); }
    assert(has_rom_text());
    draw_game_text(r,{0,0,W,H},{0,0,W,H});Pixels plain=capture(r);
    // DL2 uses its native SWORD prompt even while Watch publishes BUTTON.
    testControls=16;
    assert(SDL_RenderClear(r));draw_game_text(r,{0,0,W,H},{0,0,W,H});
    assert(capture(r)==plain);testControls=0;
    present_game(r,target);Pixels filtered=capture(r);check(plain,filtered);
    assert(game_target(r,output,false,false)==nullptr);
    // Clearing a retained ROM line removes it on the next frame.
    { std::lock_guard<std::recursive_mutex> lock(video::android_video::mutex());queue_text(2,"",20,22); }
    assert(SDL_RenderClear(r));draw_game_text(r,{0,0,W,H},{0,0,W,H});
    Pixels blank=capture(r);assert(blank!=plain);
    testControls=16;
    assert(SDL_RenderClear(r));draw_game_text(r,{0,0,320,240},{0,0,W,H});
    assert(capture(r)==blank); // Native prompt cleared: no generic replacement.
    // Calculated moves are drawn for DLE21 and Ace, using that same font path.
    for(const char *game : {"dle21","ace","sae","lair_ita","laireuro"}) {
        release_renderer(r);assert(init_text(r,bitmap,false,game,false));
        assert(SDL_RenderClear(r));draw_game_text(r,{0,0,320,240},{0,0,W,H});
        assert(capture(r)!=blank);
    }
    // Native-prompt games must stay native after switching renderer state.
    release_renderer(r);assert(init_text(r,bitmap,false,"ace91",true));
    assert(SDL_RenderClear(r));draw_game_text(r,{0,0,320,240},{0,0,W,H});
    assert(capture(r)==blank);testControls=0;
    video::set_show_fps(true);draw_hud(r,H,18.2);video::set_show_fps(false);
    SDL_Texture *retired=SDL_CreateTexture(r,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STATIC,4,4);
    assert(retired);
    { std::lock_guard<std::recursive_mutex> lock(video::android_video::mutex());retire_texture(retired);release_retired_textures(); }
    video::set_android_mobile_display(false);assert(!mobile_display());
    video::set_android_mobile_display(true);assert(mobile_display());
    SDL_Rect size={0,0,1,1};assert(resized(SDL_GetRenderWindow(r),true,size));
    assert(size.w==W && size.h==H && !resized(SDL_GetRenderWindow(r),true,size));
    video::set_android_mobile_display(false);
    assert(direct_render(r,output,output,false) && !direct_render(r,output,output,true));
    release_renderer(r);SDL_DestroySurface(bitmap);
    std::printf("Android video backend passed: retained ROM text/moves, CRT target reuse/off, sharp HUD, retirement, mobile resize and renderer cleanup.\n");
}

// Two independent painters exercise the production collection's completion
// boundary. Their simple marks make missing paints and stale alpha unambiguous.
static SDL_Renderer *scoreRenderer;
static SDL_Surface *scoreSurface;
static SDL_Texture *scoreTexture;
static unsigned scoreUploads, scorePaints[2];
namespace video {
void repaint_scoreboard_surface() {
    assert(android_video::upload_scoreboard(scoreRenderer, scoreSurface, scoreTexture));
    ++scoreUploads;
}
}
class ScorePainter : public IScoreboard {
    const int slot;
public:
    explicit ScorePainter(int index) : slot(index) {
        std::fill_n(m_DigitValues, DIGIT_COUNT, 0u);
        assert(Init());
    }
    void DeleteInstance() override { delete this; }
    void Invalidate() override { m_bNeedsRepaint = true; }
    bool ChangeVisibility(bool) override { return false; }
    bool is_repaint_needed() override { return m_bNeedsRepaint; }
    bool set_digit(unsigned value, WhichDigit digit) override { return set_digit_w_sae(value, digit); }
    bool get_digit(unsigned &value, WhichDigit digit) override { value=m_DigitValues[digit];return true; }
    bool RepaintIfNeeded() override {
        if (!m_bNeedsRepaint) return false;
        SDL_Rect rect={slot*scoreSurface->w/2,0,scoreSurface->w/4,scoreSurface->h/2};
        const Uint32 colour = m_DigitValues[PLAYER1_0]==15 ? 0 :
                SDL_MapSurfaceRGBA(scoreSurface,255,slot ? 0 : 255,slot ? 0 : 255,255);
        assert(SDL_FillSurfaceRect(scoreSurface,&rect,colour));
        ++scorePaints[slot];m_bNeedsRepaint=false;return true;
    }
};
IScoreboard *ScoreboardFactory::GetInstance(ScoreboardType type, SDL_Surface *(*)(), bool, bool, unsigned) {
    return new ScorePainter(type==IMAGE ? 0 : 1);
}
static void checkScoreboard(SDL_Renderer *renderer) {
    using namespace video::android_video;
    scoreRenderer=renderer;
    for (const char *layout : {"left","right","top"}) {
        assert(set_scoreboard_layout(layout));
        const SDL_Point size=scoreboard_size();
        assert(size.x==(horizontal_scoreboard() ? 320 : 340));
        assert(size.y==(horizontal_scoreboard() ? 32 : 480));
        scoreSurface=SDL_CreateSurface(size.x,size.y,SDL_PIXELFORMAT_RGBA32);
        assert(scoreSurface && SDL_FillSurfaceRect(scoreSurface,nullptr,0));
        scoreTexture=nullptr;scoreUploads=scorePaints[0]=scorePaints[1]=0;
        IScoreboard *collection=ScoreboardCollection::GetInstance();
        assert(ScoreboardCollection::AddType(collection,ScoreboardFactory::IMAGE));
        assert(ScoreboardCollection::AddType(collection,ScoreboardFactory::OVERLAY));
        SDL_Texture *retained=nullptr;
        for (unsigned digit : {7u,15u,8u}) {
            assert(collection->update_player_score(0,digit,0));
            assert(collection->RepaintIfNeeded());
            assert(scorePaints[0]==scoreUploads && scorePaints[1]==scoreUploads);
            if (retained) assert(retained==scoreTexture);
            retained=scoreTexture;
            const unsigned uploads=scoreUploads;
            assert(!collection->RepaintIfNeeded() && scoreUploads==uploads);
            assert(SDL_SetRenderTarget(renderer,nullptr));
            assert(SDL_SetRenderDrawColor(renderer,0,0,255,255) && SDL_RenderClear(renderer));
            assert(SDL_RenderTexture(renderer,scoreTexture,nullptr,nullptr));
            Pixels pixels=capture(renderer);
            auto pixel=[&](int x,int y,int c){return pixels[(y*W+x)*4+c];};
            // Transparent background, and clearing digits must remove old marks.
            assert(pixel(W-4,H-4,0)==0 && pixel(W-4,H-4,2)==255);
            if (digit==15) {
                assert(pixel(8,8,0)==0 && pixel(8,8,2)==255);
                assert(pixel(W/2+8,8,0)==0 && pixel(W/2+8,8,2)==255);
            } else {
                assert(pixel(8,8,0)==255 && pixel(8,8,1)==255);
                assert(pixel(W/2+8,8,0)==255 && pixel(W/2+8,8,1)==0);
            }
        }
        collection->PreDeleteInstance();
        SDL_DestroyTexture(scoreTexture);SDL_DestroySurface(scoreSurface);
    }
    scoreTexture=nullptr;scoreSurface=nullptr;scoreRenderer=nullptr;
    assert(set_scoreboard_layout("left"));
    std::printf("Shared scoreboard pipeline passed on %s: all painters finish, one upload per repaint, texture reuse, no unchanged uploads and transparent clearing in every layout.\n",SDL_GetRendererName(renderer));
}

static void scoreboard_placement() {
    using namespace video::android_video;
    SDL_Rect native = {31, 47, 200, 280};
    place_scoreboard(native, 1280);
    assert(native.x == 31 && native.y == 47 && native.w == 200 && native.h == 280);
    for (int width : {960, 1280, 1920}) {
        SDL_Rect rect = {31, 47, width / 6, width / 4};
        assert(set_scoreboard_layout("left"));
        place_scoreboard(rect, width);
        assert(rect.x == 0 && rect.y == 0 && !horizontal_scoreboard());
        assert(set_scoreboard_layout("right"));
        place_scoreboard(rect, width);
        assert(rect.x + rect.w == width && rect.y == 0 && !horizontal_scoreboard());
        assert(set_scoreboard_layout("top"));
        place_scoreboard(rect, width);
        assert(rect.x == 0 && rect.y == 0 && rect.w == width && rect.h == width / 10);
        assert(horizontal_scoreboard());
        assert(!set_scoreboard_layout("invalid") && horizontal_scoreboard());
    }
    assert(set_scoreboard_layout("left"));
}

int main() {
    scoreboard_placement();
    SDL_SetHint(SDL_HINT_VIDEO_DRIVER,"offscreen");
    assert(SDL_Init(SDL_INIT_VIDEO));
    SDL_Window *window=SDL_CreateWindow("CRT final frame test",W,H,SDL_WINDOW_OPENGL|SDL_WINDOW_HIDDEN);
    assert(window);
    SDL_Renderer *r=SDL_CreateRenderer(window,"opengles2");
    if(!r){std::fprintf(stderr,"GLES2 renderer: %s\n",SDL_GetError());return 1;}
    assert(android_crt_available(r));
    SDL_Texture *target=SDL_CreateTexture(r,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_TARGET,W,H);
    assert(target && SDL_SetTextureBlendMode(target,SDL_BLENDMODE_NONE));
    SDL_Texture *yuv=SDL_CreateTexture(r,SDL_PIXELFORMAT_IYUV,SDL_TEXTUREACCESS_STREAMING,64,48);
    assert(yuv);
    Pixels y(64*48,126),uv(32*24,128);
    assert(SDL_UpdateYUVTexture(yuv,nullptr,y.data(),64,uv.data(),32,uv.data(),32));
    SDL_Texture *white=font(r,SDL_PIXELFORMAT_RGBA32,true);
    SDL_Texture *rgba=font(r,SDL_PIXELFORMAT_RGBA32,false);
    SDL_Texture *bgra=font(r,SDL_PIXELFORMAT_BGRA32,false);
    SDL_FRect picture={8,8,112,80}, glyph={24,24,32,32};
    for(int repeat=0;repeat<3;++repeat) {
        assert(SDL_SetRenderTarget(r,target));
        assert(!android_crt_present(r,target)); // Must finish composition first.
        assert(SDL_SetRenderDrawColor(r,0,0,0,255) && SDL_RenderClear(r));
        assert(SDL_RenderTexture(r,yuv,nullptr,&picture));
        assert(SDL_RenderTexture(r,white,nullptr,&glyph));
        assert(SDL_SetTextureAlphaMod(rgba,128));
        SDL_FRect colour={60,12,32,32};
        assert(SDL_RenderTextureRotated(r,rgba,nullptr,&colour,90,nullptr,SDL_FLIP_NONE));
        SDL_Rect clip={64,40,20,16};assert(SDL_SetRenderClipRect(r,&clip));
        colour={60,36,32,32};assert(SDL_RenderTexture(r,bgra,nullptr,&colour));
        assert(SDL_SetRenderClipRect(r,nullptr));
        assert(SDL_SetRenderDrawColor(r,255,255,255,255));
        assert(SDL_RenderDebugText(r,2,58,"ROM TEXT"));
        SDL_FRect marker={90,2,12,4};
        assert(SDL_SetRenderDrawColor(r,255,0,0,255) && SDL_RenderFillRect(r,&marker));
        Pixels plain=capture(r);
        assert(SDL_SetRenderTarget(r,nullptr));
        auto hud=[&] {
            assert(SDL_SetRenderDrawColor(r,255,255,255,255));
            assert(SDL_RenderDebugText(r,2,78,"FPS: 30"));
            SDL_FRect score={90,4,24,24};
            assert(SDL_RenderTexture(r,white,nullptr,&score));
        };
        assert(SDL_RenderTexture(r,target,nullptr,nullptr));
        hud();Pixels plainHud=capture(r);
        assert(android_crt_present(r,target));
        Pixels filtered=capture(r);
        check(plain,filtered);
        assert(plain!=filtered);
        hud();Pixels withHud=capture(r);
        int whiteHudPixels=0;
        for(int yy=0;yy<H;++yy)for(int xx=0;xx<W;++xx) {
            if(yy<78 && !(xx>=90 && xx<114 && yy>=4 && yy<28))continue;
            int i=(yy*W+xx)*4;
            if(plainHud[i]==255 && plainHud[i+1]==255 && plainHud[i+2]==255) {
                for(int c=0;c<3;++c)assert(withHud[i+c]==255);
                ++whiteHudPixels;
            }
        }
        assert(whiteHudPixels>100); // Added score/lives glyphs and FPS stay sharp.
        // SDL must recover its draw state after the raw GLES draw, including
        // across repeated target switches (the production frame loop).
        marker={90,70,10,10};
        assert(SDL_SetRenderDrawColor(r,0,255,0,255) && SDL_RenderFillRect(r,&marker));
        Pixels restored=capture(r);
        assert(restored[(74*W+94)*4]==0 && restored[(74*W+94)*4+1]==255);
        assert(glGetError()==GL_NO_ERROR);
        SDL_RenderPresent(r);
    }
    checkText(r);
    checkBackend(r);
    checkMoveSources(r);
    checkScoreboard(r);
    SDL_Texture *small=SDL_CreateTexture(r,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_TARGET,16,16);
    assert(small && !android_crt_present(r,small));SDL_DestroyTexture(small);
    SDL_Surface *surface=SDL_CreateSurface(W,H,SDL_PIXELFORMAT_RGBA32);
    SDL_Renderer *software=SDL_CreateSoftwareRenderer(surface);
    assert(software && !android_crt_available(software));
    checkText(software);
    checkMoveSources(software);
    checkScoreboard(software);
    SDL_DestroyRenderer(software);SDL_DestroySurface(surface);
    android_crt_reset(r);
    SDL_DestroyTexture(target);SDL_DestroyTexture(white);SDL_DestroyTexture(rgba);
    SDL_DestroyTexture(bgra);SDL_DestroyTexture(yuv);
    SDL_DestroyRenderer(r);SDL_DestroyWindow(window);SDL_Quit();
    std::printf("CRT final-frame GPU checks passed: every pixel matches reference, YUV, transparent text, native text font, sharp FPS/score HUD, RGBA/BGRA, alpha, clipping, rotation, SDL state and fallback.\n");
}
