# Earlier versions

The three architectures this project went through before the current one. They are kept for
reference — the revived stack deliberately reuses their names, Redis key names and wire
protocol — and none of them runs as-is, because the AWS resources behind v2 and v3 no longer
exist.

| version | shape | what it added |
|---|---|---|
| [`v1/`](v1/) | two Node services (static files + WebSocket) in Docker on one EC2 instance | the first working canvas; drawing history lived in process memory |
| [`v2/`](v2/) | Lambda + managed Redis, hosted frontend, API Gateway WebSocket | state moved out of the process, so a restart stopped erasing the canvas |
| [`v3/`](v3/) | API Gateway WebSocket, four Lambdas, ElastiCache, two SQS queues, S3 + CloudFront | the full serverless design: separate connect/draw/disconnect handlers, ordered queue for PNG writes, static assets on a CDN |

`v1/README.md`, `v2/notes.txt` and `v3/README.md` are the notes written at the time; each
version's `architecture.png` is its diagram.

Built by Jesse Xu, Ziao Liu and Leon Liang.
