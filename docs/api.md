# Glyco API

Base URL: `/api`

Core endpoints:

- `POST /users/demo`
- `GET /users/{user_id}`
- `POST /profiles`
- `GET /profiles/{user_id}`
- `PUT /profiles/{profile_id}`
- `POST /risk-assessment`
- `GET /risk-assessment/{user_id}/latest`
- `POST /logs`
- `GET /logs/{user_id}`
- `POST /monitoring-assessment?user_id=1`
- `GET /monitoring-assessment/{user_id}/latest`
- `POST /reports/{doctor|family|weekly}?user_id=1`
- `GET /reports/{user_id}`
- `POST /agent/chat`
- `POST /agent/feedback`
- `GET /agent/llm-status`
- `GET /agent/insight/{user_id}`
- `POST /agent/proactive-check/{user_id}`
- `GET /alerts/{user_id}`
- `POST /care-plan/diet?user_id=1`
- `POST /family-shares`
- `GET /family-shares/{share_token}`

All risk and monitoring responses are support guidance, not diagnostic output.

Agent feedback payload:

- `user_id`
- `message`
- `helpful`
- `preferred_tone`
- `confirmed_action`
- `notes`

The feedback endpoint stores personalization signals that the agent reads back as `learning_summary` during future chat responses.
