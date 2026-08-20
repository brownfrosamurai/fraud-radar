# Demo GIF

`demo.gif` is a screen capture of `http://localhost:3000` after `docker compose up --build`.

Beats: idle feed → burst 50/2s → stats/charts move → flagged row → permutation bars.

Encode from a 1280px-wide recording:

```bash
ffmpeg -i demo.mov -vf "fps=12,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 assets/demo.gif
gifsicle -O3 --lossy=80 assets/demo.gif -o assets/demo.gif
```

Cap: 8 MB. Not generated in CI.
