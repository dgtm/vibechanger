# Vibechanger

Vibechanger is my shot at a video voice-style transformation pipeline.

It takes an input video, transcribes its audio, rewrites the transcript to a target tone, synthesizes new speech with CosyVoice3 using the speaker's own reference sample, and runs MuseTalk to produce a lip-synced output video.

## How do you do that

Whisper, CosyVoice3, MuseTalk

## Repo Structure

- `jobs/video_ai/`: main worker image and runtime pipeline.
- `jobs/hf_downloader/`: model downloader job for Hugging Face / direct URLs.
- `scripts/run_video_model.sh`: Cloud Run Job execution + log tailing wrapper.
- `terraform/`: infra for jobs, buckets, IAM, and related resources.
- `ui/`: local web UI for uploads/triggering job workflows.
- `local/`: local helper scripts and sample inputs/outputs.

## Main Commands

Show all commands:

```bash
make help
```

Auth/project setup:

```bash
make auth-login
make auth-project PROJECT_ID=<your-project-id>
```

Build and publish images:

```bash
make docker-publish
```


Terraform workflow:

```bash
make terraform-init
make terraform-plan
make terraform-apply
```

Run the local UI to record your video

```bash
make ui
```

Or Use local input to give it a spin

```bash
make run
```

Download default model set to the models bucket:

```bash
make hf-download
```


## Inputs and Outputs

- Local default input video: `local/input/input.mp4`
- Local output directory: `local/output/`
- Cloud job data paths are mounted under `/data` in the container.
- Model assets are mounted/read from `/models` in the container.

## Challenges
I use Google Cloud Run jobs, its ephemeral and just easier to terraform. Models are backed by the cloud storage which can be loaded to the containers on runtime. Bootup time and Image size is still a bit harsh, separating the steps would need a messaging layer between them.
