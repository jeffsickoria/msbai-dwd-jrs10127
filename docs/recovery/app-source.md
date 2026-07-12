# Recovered Application Source

The four application files in the repository root —

- `app.py`
- `query.py`
- `Dockerfile`
- `requirements.txt`

— were **recovered exactly** from the deployed Cloud Run build context. They are **not** a
reconstruction from memory. They are byte-for-byte identical to the source that produced the
currently-running `citibike-app` image.

## Source object (GCS)

| Field | Value |
|---|---|
| Object | `gs://bigdataday1/cloudbuild-source/citibike-app.tar.gz` |
| Bucket | `bigdataday1` |
| Size | 4913 bytes |
| Generation | `1781182032235988` |
| Created / Updated | `2026-06-11T12:47:12.357Z` |
| Content type | `application/gzip` |
| MD5 (base64, from GCS) | `jkLszmtbGo3k45TUwgmdBw==` |
| CRC32C (from GCS) | `XAvVBA==` |
| **Archive SHA-256** | `b1e8ff3a8b7a36d7757779be1c1d20a461a51cc4b542392ee52c00c168cf9c90` |

The downloaded archive's MD5 was verified equal to the GCS object's `md5Hash`, confirming the
download is byte-identical to the stored object.

## Recovered file checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `app.py` | `d7d1f9f0b4148d22aaa86ed1e172ed6546362e7c8d667cf48eeacf1b1f4c84cc` |
| `query.py` | `8e8a28bfa02e51eb14324b985bec7e244b76608a352c3a95513d343761adc3fd` |
| `Dockerfile` | `a691fbac8921d9bfffde3d3e597956d406044f18008dd7a7680d381a20bbd985` |
| `requirements.txt` | `df9eb9fe73c3ff9e40e64393b7b7dee74b70e5149bebed5b261da14feab5cbeb` |

The files committed to the repository were re-hashed after extraction and match the archive
contents exactly.

## Archive safety validation (performed before extraction)

- Archive contains **exactly** the four expected files — no extra entries.
- No absolute paths.
- No `../` path traversal.
- No symlinks/hardlinks — all entries are regular files.

## Cloud Run deployment this source corresponds to

| Field | Value |
|---|---|
| Service | `citibike-app` |
| Region | `us-central1` |
| Current image digest | `us-central1-docker.pkg.dev/msbai-dwd-jrs10127/citibike/app@sha256:04dbc01ab2294053f5ec71b8a5172d28fae24c296bc21e1016d479dc8dcce2df` |
| Public URL | https://citibike-app-kpkbtfmmcq-uc.a.run.app |

## Local verification (read-only, no cloud changes)

- `python3 -m py_compile app.py query.py` — both compile without syntax errors.
- BigQuery objects referenced by the app:
  - `nyu-datasets.citibike.m_daily_trips` (shared course dataset — main charts)
  - `nyu-datasets.weather.m_weather_daily_nyc` (shared course weather table — joined by `date`)
  - `msbai-dwd-jrs10127.citibike.trips_daily_model` (this project's model output — "is it us or the weather?" section)
- Hard-coded configuration (left unchanged, documented for awareness):
  - BigQuery client project `msbai-dwd-jrs10127` in both `app.py` and `query.py`
  - The three fully-qualified table/view names above
  - Rider-type → column map (`member`→`num_member_trips_nyc`, `casual`→`num_casual_trips_nyc`, `all`→`num_nyc_trips`)
  - `@st.cache_data(ttl=3600)` query cache TTL
  - Container `PORT` defaults to `8080`
- Dependency notes: `db-dtypes` is an implicit runtime dependency for BigQuery→pandas
  `.to_dataframe()`; `statsmodels` is listed in `requirements.txt` but is **not** imported by
  `app.py` or `query.py` (it belongs to the separate model-fitting step, which is not part of this
  deployed build context).

## Recovery metadata

- **Recovery date:** 2026-07-12
- **Method:** authenticated read of the GCS build context via the `cloud-bootstrap` service
  account (`claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com`); download to ephemeral
  session storage; validated; extracted. No BigQuery, GCS, Cloud Run, IAM, or Artifact Registry
  resource was modified. No credentials, tokens, or secret values are included in this document.
