# Liquid Software

Sitebuilder for composing a site from features and generating a folder that can run on its own. This is a new Python application. The behavior it keeps comes from the old ASP.NET Sitebuilder and the Gateway Hotel reservation desk. The old source was compromised, so the parts that could hide a back door were not ported. See [SECURITY.md](SECURITY.md).

The recovered archives were Visual Basic .NET, not C. The namespace was Sitebuilder. This edition keeps that name for the staff desk.

## Run

```bash
python -m pip install -r requirements.txt
python -m liquid
```

Open `http://127.0.0.1:8000`.

In development the first launch creates:

- Email `builder@liquidsoftware.local`
- Password `ChangeMe!Liquid2026`, unless `LIQUID_BOOTSTRAP_PASSWORD` is set

Set a real secret and password before anyone else can reach the host. Copy `.env.example` to `.env`.

```bash
LIQUID_ENV=production
LIQUID_SECRET_KEY=at-least-32-random-characters
LIQUID_BOOTSTRAP_PASSWORD=a-long-password-with-Mixed-case-1
LIQUID_COOKIE_SECURE=true
LIQUID_ALLOWED_HOSTS=builder.example
```

Production refuses to start without `LIQUID_SECRET_KEY`, and refuses the first boot without `LIQUID_BOOTSTRAP_PASSWORD`.

## What Sitebuilder does

1. Sign in and create a site.
2. Turn features on: pages, menus, search, files, help, forms, customer accounts, catalog, hotel reservations, news, banners, calendar, services, gallery, courses, RV coaches, coupons, tell-a-friend, and the local message queue.
3. Draft a page, publish it, or revert the draft back to the live copy. Editors can save drafts. Publishers publish and generate.
4. For a hotel site, set the property, room inventory, and guest details. Availability counts nights that actually overlap, inside a single save.
5. Generate. The result is `data/generated/<slug>/` and a zip download. Published news, events, services, courses, coaches, coupons, and albums are included. Quiz grading, merchant approval, and the message queue stay in Sitebuilder.

The generated folder is a separate FastAPI app:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8080
```

On Windows, Waitress can sit behind IIS:

```bash
python -m waitress --listen=127.0.0.1:8080 app:app
```

Put TLS in front of either server. Reservations created on the generated site stay in that folder's `site.db`. Generating again replaces the source snapshot; deploy the zip somewhere else before you regenerate if you need to keep a running copy.

The sample site is Gateway Hotel, with a standard king room and a king suite. Preview it at `/s/gateway`.

## Tests

```bash
python -m pytest
```

## Staff roles

| Role | Can |
| --- | --- |
| Owner | Features, staff, deletion, everything below |
| Publisher | Publish, generate, hotel, catalog |
| Editor | Drafts, files, forms, help |
| Hotel | Property, rooms, reservations |
