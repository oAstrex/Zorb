import os
import re
from dataclasses import dataclass
from config import cfg


TV_PATTERN = re.compile(r"(.*?)[ ._-]*S(\d{1,2})E(\d{1,2})", re.IGNORECASE)


@dataclass
class MediaOrganizer:
    def get_save_path_for_category(self, category: str) -> str:
        if category == cfg.CATEGORY_TV:
            return cfg.MEDIA_TV_PATH
        if category == cfg.CATEGORY_MOVIES:
            return cfg.MEDIA_MOVIES_PATH
        return cfg.MEDIA_MOVIES_PATH

    def build_output_path(self, job: dict, file_rel_path: str) -> str:
        """
        Build final .strm path per rules:
        - TV: /data/media/tv/{Show Name}/Season {number}/{Show.Name.SxxEyy}.strm
        - Movies: /data/media/movies/{Movie Name (Year)}/{Movie.Name.(Year)}.strm
        """
        category = job.get("category", cfg.CATEGORY_MOVIES)
        name = job.get("name", "Unknown")
        base_dir = self.get_save_path_for_category(category)

        if category == cfg.CATEGORY_TV:
            m = TV_PATTERN.search(name) or TV_PATTERN.search(file_rel_path)
            show = name
            season_num = 1
            episode_num = 1
            if m:
                show = m.group(1).strip(" ._-")
                try:
                    season_num = int(m.group(2))
                    episode_num = int(m.group(3))
                except Exception:
                    pass
            show_dir = os.path.join(base_dir, show)
            season_dir = os.path.join(show_dir, f"Season {season_num:02d}")
            os.makedirs(season_dir, exist_ok=True)
            out_name = re.sub(r"[^A-Za-z0-9._ -]", "", name)
            if not TV_PATTERN.search(out_name):
                out_name = f"{show}.S{season_num:02d}E{episode_num:02d}"
            out_path = os.path.join(season_dir, f"{out_name}.strm")
            return out_path

        # Movies
        m = re.search(r"(.*?)[ ._-]*\(?((19|20)\d{2})\)?", name)
        if m:
            title = m.group(1).strip(" ._-")
            year = m.group(2)
            dir_name = f"{title} ({year})"
            out_base = os.path.join(base_dir, dir_name)
            os.makedirs(out_base, exist_ok=True)
            file_name = f"{title} ({year}).strm"
        else:
            title = re.sub(r"[._]", " ", name).strip()
            out_base = os.path.join(base_dir, title)
            os.makedirs(out_base, exist_ok=True)
            file_name = f"{title}.strm"

        out_path = os.path.join(out_base, file_name)
        return out_path