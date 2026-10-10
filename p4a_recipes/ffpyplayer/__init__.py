from pythonforandroid.recipe import PyProjectRecipe, Recipe
from os.path import join


class FFPyPlayerRecipe(PyProjectRecipe):
    version = 'v4.5.1'
    url = 'https://github.com/matham/ffpyplayer/archive/{version}.zip'
    depends = ['python3', 'sdl2', 'ffmpeg']
    patches = ["setup.py.patch"]
    opt_depends = ['openssl', 'ffpyplayer_codecs']

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        # حذف بلوک avfft.h از ffmpeg.pxi (در FFmpeg 8 حذف شده؛ کد مرده است)
        # مستقیم با پایتون انجام می‌شود تا مشکل کش پچ دور زده شود
        import os
        pxi = join(self.get_build_dir(arch.arch), 'ffpyplayer',
                   'includes', 'ffmpeg.pxi')
        if os.path.exists(pxi):
            with open(pxi, 'r') as f:
                content = f.read()
            old_block = '''    extern from "libavcodec/avfft.h" nogil:
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
            if old_block in content:
                content = content.replace(old_block, '')
                with open(pxi, 'w') as f:
                    f.write(content)

    def get_recipe_env(self, arch, with_flags_in_cc=True):
        env = super().get_recipe_env(arch)
        build_dir = Recipe.get_recipe('ffmpeg', self.ctx).get_build_dir(arch.arch)
        env["FFMPEG_INCLUDE_DIR"] = join(build_dir, "include")
        env["FFMPEG_LIB_DIR"] = join(build_dir, "lib")
        env["SDL_INCLUDE_DIR"] = join(self.ctx.bootstrap.build_dir, 'jni', 'SDL', 'include')
        env["SDL_LIB_DIR"] = join(self.ctx.bootstrap.build_dir, 'libs', arch.arch)
        env["USE_SDL2_MIXER"] = '1'
        sdl2_mixer_recipe = self.get_recipe('sdl2_mixer', self.ctx)
        env["SDL2_MIXER_INCLUDE_DIR"] = sdl2_mixer_recipe.get_include_dirs(arch)[0]
        env['NDKPLATFORM'] = "NOTNONE"
        env['LIBLINK'] = 'NOTNONE'
        if 'ffpyplayer_codecs' not in self.ctx.recipe_build_order:
            env["CONFIG_POSTPROC"] = '0'
        return env

recipe = FFPyPlayerRecipe()
