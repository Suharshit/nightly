"""Entry point for the Hugging Face Gradio Space (Docker Spaces are paid; Gradio CPU is free).

The Space runs `python app.py`. Gradio's server is FastAPI, so the nightly API is served as
it is, with a one-line Gradio page mounted at /ui. API routes are matched first.
"""

import gradio as gr
import uvicorn

from api.app.main import app

with gr.Blocks(title="nightly API") as ui:
    gr.Markdown("The API behind [nightly](https://nightlyjobs.vercel.app). "
                "Health check: [/health](/health).")

app = gr.mount_gradio_app(app, ui, path="/ui")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
