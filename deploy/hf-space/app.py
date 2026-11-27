"""Entry point for the Hugging Face Space.

Free accounts can only create Gradio Spaces on ZeroGPU hardware. The Space runs `python app.py`.
Gradio's server is FastAPI, so the nightly API is served as it is, with a one-line Gradio page
mounted at /ui (API routes are matched first). The models run on CPU; no GPU is ever requested.
"""

try:  # Only installed on ZeroGPU. It must be imported before torch.
    import spaces
except ImportError:
    spaces = None

import gradio as gr
import uvicorn

from api.app.main import app

if spaces is not None:
    @spaces.GPU
    def _unused() -> None:
        """ZeroGPU expects at least one @spaces.GPU function at startup. Never called, so no
        GPU quota is used."""


with gr.Blocks(title="nightly API") as ui:
    gr.Markdown("The API behind [nightly](https://nightlyjobs.vercel.app). "
                "Health check: [/health](/health).")

app = gr.mount_gradio_app(app, ui, path="/ui")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
