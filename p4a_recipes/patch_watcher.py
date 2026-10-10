#!/usr/bin/env python3
"""واچر: به‌محض دانلود سورس ffpyplayer، فایل ffmpeg.pxi را پچ می‌کند."""
import os, time, glob

OLD_BLOCK = '''    extern from "libavcodec/avfft.h" nogil:
        enum RDFTransformType:
            DFT_R2C,
            IDFT_C2R,
            IDFT_R2C,
            DFT_C2R,
        struct RDFTContext:
            pass
        void av_rdft_end(RDFTContext *)
        RDFTContext *av_rdft_init(int, RDFTransformType)
        void av_rdft_calc(RDFTContext *, FFTSample *)

'''

patched = set()
while True:
    for pxi in glob.glob('.buildozer/**/ffpyplayer/**/includes/ffmpeg.pxi', recursive=True):
        if pxi in patched:
            continue
        try:
            with open(pxi, 'r') as f:
                content = f.read()
        except:
            continue
        if 'libavcodec/avfft.h' in content and OLD_BLOCK in content:
            content = content.replace(OLD_BLOCK, '')
            with open(pxi, 'w') as f:
                f.write(content)
            print(f'[watcher] patched {pxi}', flush=True)
            patched.add(pxi)
    time.sleep(3)
