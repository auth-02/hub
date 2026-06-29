# In-app notifications system

> A complex feature — user-facing notifications spanning data model, storage,
> delivery, API, and UI — decomposed into one tight bottom-up stack. Each layer
> answers a single reviewable question and can't be built until the layer below
> it is tested.

## Stack

```
notifications/schema            ← implement first (table + enums + migration)
      ↑
notifications/store             (create / mark-read / list, paginated)
      ↑
notifications/emit-service      (one place that raises a notification)
      ↑
notifications/delivery-workers  (fan out: in-app now, email/push async)
      ↑
notifications/api               (REST: list, unread-count, mark-read)
      ↑
notifications/ui                ← implement last (bell, dropdown, read state)
```

| Layer | What it does | Depends on | Reviewable question | Status |
|-------|-------------|------------|---------------------|--------|
| `notifications/schema` | `notifications` table (`user_id`, `type`, `payload`, `read_at`) + migration | — | Are the type enum and indexes right for unread-count queries? | open |
| `notifications/store` | Data-access layer: `create`, `list(user, cursor)`, `mark_read`, `unread_count` | schema | Is listing paginated and unread-count cheap (indexed)? | open |
| `notifications/emit-service` | Single `notify(user, type, payload)` entry point used by the rest of the app | store | Is there exactly one way to raise a notification? | open |
| `notifications/delivery-workers` | In-app write synchronously; email/push enqueued to a background worker | emit-service | Does a slow email channel never block the in-app notification? | open |
| `notifications/api` | `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/:id/read` | store | Are responses scoped to the authenticated user only? | open |
| `notifications/ui` | Bell with unread badge, dropdown list, mark-read on open | api | Does the badge update without a full page reload? | open |
