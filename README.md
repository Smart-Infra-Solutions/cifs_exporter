# cifs_exporter

Conteneur qui scanne un partage CIFS **déjà monté** sur l'hôte, et détermine
quels fichiers sont réellement **utilisés** (accédés) vs **inutilisés depuis
longtemps**, afin d'aider à faire le ménage sur un gros partage.

Il produit :
- des **métriques Prometheus** (`/metrics`) consommables par Grafana
- un **rapport fichier** (`report.csv` + `summary.json`) listant les candidats
  au nettoyage

Le conteneur ne fait **que lire** le partage — il ne supprime, ne déplace et ne
modifie jamais aucun fichier. Le ménage reste une action manuelle.

## ⚠️ Limite importante : atime

La détection "utilisé" repose sur l'évolution de l'**access time (atime)** des
fichiers d'un scan à l'autre. Si le partage/serveur source ne met pas à jour
l'atime (`noatime` côté client CIFS, ou "last access time" désactivé côté
serveur Windows — c'est le **défaut** depuis Windows Vista/Server 2008 pour des
raisons de performance), l'atime ne bougera jamais et **tout paraîtra inutilisé
à tort**.

Avant de faire confiance au rapport pour supprimer quoi que ce soit :
- Vérifiez côté serveur Windows : `fsutil behavior query disablelastaccess`
  (`0` = activé, tracking OK). Pour l'activer : `fsutil behavior set disablelastaccess 0`.
- Vérifiez que le point de montage CIFS côté hôte n'utilise pas l'option `noatime`.
- Laissez tourner l'exporter **au moins `STALE_DAYS`** avant de considérer le
  statut `stale` comme fiable : les fichiers vus pour la première fois restent
  classés `unknown` tant qu'on n'a pas assez de recul.

## Utilisation

```bash
docker compose -f docker-compose.example.yml up -d --build
curl http://localhost:9877/metrics
cat /var/lib/docker/volumes/cifs_exporter_state/_data/report.csv
```

Voir `docker-compose.example.yml` pour un exemple complet (bind mount du
partage en lecture seule, volume séparé pour l'état).

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `CIFS_PATH` | *(obligatoire)* | Chemin du partage CIFS déjà monté, à scanner |
| `STATE_DB_PATH` | `/data/state/state.db` | Base SQLite d'état — doit être **hors** du partage CIFS, sur un volume persistant |
| `REPORT_DIR` | `/data/state` | Dossier de sortie de `report.csv` / `summary.json` |
| `SCAN_INTERVAL_SECONDS` | `86400` | Intervalle entre deux scans (secondes) |
| `STALE_DAYS` | `90` | Seuil d'inactivité pour classer un fichier `stale` |
| `METRICS_PORT` | `9877` | Port HTTP d'exposition des métriques Prometheus |
| `EXCLUDE_GLOBS` | *(vide)* | Motifs glob séparés par des virgules à exclure (ex: `*.tmp,~$*,Thumbs.db`) |
| `FOLLOW_SYMLINKS` | `false` | Suivre les liens symboliques pendant le scan |
| `RUN_ONCE` | `false` | Fait un seul scan puis quitte (utile en test, ou avec un cron externe) |
| `LOG_LEVEL` | `INFO` | Niveau de log Python |

## Métriques exposées

- `cifs_exporter_scan_timestamp_seconds`, `cifs_exporter_scan_duration_seconds`
- `cifs_exporter_scan_errors_total`
- `cifs_exporter_files_total`, `cifs_exporter_files_used`,
  `cifs_exporter_files_stale`, `cifs_exporter_files_unknown`
- `cifs_exporter_bytes_total`, `cifs_exporter_bytes_stale`

## Rapport

- `report.csv` : une ligne par fichier actif — `path`, `size_bytes`,
  `first_seen_iso`, `last_atime_iso`, `last_used_at_iso`,
  `days_since_last_use`, `first_seen_days_ago`, `status` (`used`/`stale`/`unknown`)
- `summary.json` : compteurs globaux et octets récupérables estimés

## CI/CD

Le pipeline Woodpecker (`.woodpecker/docker-publish.yml`) build l'image et la push sur Docker
Hub sous `smartinfrasolutions/cifs_exporter` :
- push sur `main` → tag `latest`
- push d'un tag `vX.Y.Z` → tags de version (+ `latest`) via `auto_tag`

Nécessite le secret Woodpecker `docker_token` (mot de passe/token du compte
Docker Hub `smartinfrasolutions`).

## Développement local

```bash
python -m venv .venv && .venv\Scripts\activate  # ou source .venv/bin/activate
pip install -r requirements.txt
CIFS_PATH=./test-share RUN_ONCE=true python -m cifs_exporter.main
```
