from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if version == "editable":
            return
        static = Path(self.root) / "src" / "alc_web" / "static"
        if not (static / "index.html").is_file():
            raise RuntimeError(
                "Build apps/web with npm ci && npm run build before packaging alc-web."
            )
        build_data.setdefault("force_include", {})[str(static)] = (
            "alc_web/static" if self.target_name == "wheel" else "src/alc_web/static"
        )
