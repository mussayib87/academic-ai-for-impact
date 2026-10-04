# Security

Passwords use Argon2 through `pwdlib`; JWT signing algorithm, secret, and expiry are configuration values. Production settings reject obvious placeholder secrets. Never commit `.env`; `.env.example` contains only placeholders. Demo credentials are restricted to the explicit fictional seed command.

Private routes use `get_current_user`, `get_current_teacher`, or `get_current_student`. Teacher views/actions enforce teacher role. Student APIs resolve the linked `Student.user_id`; profile, submissions, feedback, and file access are filtered to that owner. Requests for another student's profile return not found.

CORS origins are explicit and reject wildcard values because credentials are enabled. Uploads are extension- and size-limited, use random filenames in an isolated directory, check resolved download paths, and are never executed. Inline preview is limited to PDF, PNG/JPEG/GIF/WebP, and plain text to avoid active content.

Important limitations: production deployment still needs institution-specific retention, encryption-at-rest, rate limiting, secret rotation, backup, monitoring, privacy review, and formal authorization policy. Do not put real student records in this demo.