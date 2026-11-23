# GUI Assets

The 50 character portrait PNGs in `sprites/avatars/` (`1.png` through `50.png`)
are original assets procedurally generated for Khoa's Pygame GUI using
`generate_avatars.py` (Python + Pillow, 256×256 RGBA circular character tokens).

No external or third-party artwork is copied into this directory. To regenerate
the full avatar set deterministically:

```powershell
python src/assets/generate_avatars.py
```
