#include "config.h"

#include "scoreboard_factory.h"
#ifdef __ANDROID__
#include "../video/video_android.h"
#endif
#include "hw_scoreboard.h"
#include "usb_scoreboard.h"
#include "null_scoreboard.h"
#include "img_scoreboard.h"
#include "bezel_scoreboard.h"
#include "overlay_scoreboard.h"

IScoreboard *ScoreboardFactory::GetInstance(ScoreboardType type,
		SDL_Surface *(*pFuncGetActiveOverlay)(),
		bool bThayers, bool bUsingAnnunciator, unsigned int uWhichPort)
{
	IScoreboard *pRes = 0;

	switch (type)
	{
	default:	// NULL
		pRes = NullScoreboard::GetInstance();
		break;
	case IMAGE:
#ifdef __ANDROID__
        if (video::android_video::horizontal_scoreboard()) {
            pRes = OverlayScoreboard::GetInstance(pFuncGetActiveOverlay, bThayers, true);
        } else {
            pRes = ImgScoreboard::GetInstance(bThayers);
        }
#else
        pRes = ImgScoreboard::GetInstance(bThayers);
#endif
        break;
	case OVERLAY:
		pRes = OverlayScoreboard::GetInstance(pFuncGetActiveOverlay, bThayers);
		break;
	case HARDWARE:	// hardware scoreboard via parallel port
		pRes = HwScoreboard::GetInstance(uWhichPort);
		break;
	case BEZEL:
		pRes = BezelScoreboard::GetInstance();
		break;
	case USB:	// Hardware scoreboard via USB
	        pRes = USBScoreboard::GetInstance();
		break;
	}
	// set the annunciator value while we're here
	if (pRes != NULL)
	{
		pRes->m_bUsingAnnunciator = bUsingAnnunciator;
	}

	return pRes;
}
