# Site Internet — learningtrip.fr

Site vitrine statique : 1 page d'accueil (vidéo, simulateur de budget,
brochure gated) + 1 page par séjour. Aucune dépendance externe (pas de
framework, pas de build npm, aucune requête vers un service tiers au
chargement) — tout est généré par `build_site.py`.

> **Dossier autonome.** Tout le nécessaire (contenu, branding, images,
> migration Supabase) est inclus ici : ce dossier peut être copié tel quel
> dans un dépôt dédié et fonctionner sans le reste du projet Learning Trip.

## Démarrage rapide

```
python3 serve.py            # → http://127.0.0.1:8765 (ouvre le navigateur)
```

Pour regénérer le site après modification du contenu :

```
python3 -m pip install -r requirements.txt   # une fois (Pillow, pour les photos)
python3 build_site.py
```

## Structure

```
Site Internet/
  serve.py                 lance le site en local pour le visualiser (+ page 404)
  requirements.txt         dépendances Python du BUILD (Pillow)
  data/destinations.json   ← SOURCE DE VÉRITÉ : tout le contenu éditable (+ SEO du site)
  data/sitemap-state.json  GÉNÉRÉ : date de dernière modification réelle de chaque page
  templates/               index.html · sejour.html · legal.html · cgv.html · 404.html · brochure.html
  build_site.py            génère pages, variantes d'images, JS minifié, sitemap, robots…
  fetch_photos.py          photos Wikimedia Commons (libres, crédits inclus)
  netlify.toml             cache, redirections des anciennes URL, page 404
  index.html  sejours/  mentions-legales.html  cgv.html  404.html  ← GÉNÉRÉS
  sitemap.xml  robots.txt  site.webmanifest                        ← GÉNÉRÉS
  supabase/migrations/     0006_site_leads.sql ← schéma de la table des leads
  docs/                    audit performance & SEO
  assets/
    css/site.css           design system (couleurs du logo : #053c64 / #c9f8fe)
    css/fonts.css          @font-face des polices auto-hébergées
    fonts/                 Poppins + Inter en woff2 (SIL Open Font License)
    js/site.js             SOURCE : simulateur · formulaires leads · animations
    js/site.min.js         GÉNÉRÉ (seul fichier JS chargé par les pages)
    js/config.js           URL + clé publique Supabase (clé publishable = OK côté client)
    js/destinations.js     GÉNÉRÉ depuis data/destinations.json
    img/logo.png  favicon.png  og-image.png  apple-touch-icon.png  icon-192/512.png
    img/destinations/      photos + credits.json
    opt/                   GÉNÉRÉ : variantes AVIF / WebP / JPEG des images
    brochure/              brochure.html (GÉNÉRÉ) + Brochure-Learning-Trip.pdf
```

## Modifier le contenu

1. Éditer `data/destinations.json` (textes, expériences, moments, infos pratiques).
2. `python3 build_site.py`
3. Regénérer le PDF de la brochure si elle a changé :
   ```
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
     --no-pdf-header-footer \
     --print-to-pdf="assets/brochure/Brochure-Learning-Trip.pdf" \
     "file://$PWD/assets/brochure/brochure.html"
   ```

⚠️ Ne jamais éditer `index.html`, `sejours/*.html`, `mentions-legales.html`,
`cgv.html`, `404.html` ni `assets/js/site.min.js` à la main : ils sont écrasés par le
build. Éditer `templates/`, `data/`, `assets/css/site.css`, `assets/js/site.js`.

## Performance & SEO : ce que fait le build (à respecter)

Détails et mesures : `docs/audit-performance-seo.md`.

- **Relancer `python3 build_site.py` après toute modification** d'un template,
  du CSS, du JS ou d'une image : le CSS est inliné dans chaque page (réduit aux
  règles qu'elle utilise), `site.js` est minifié, et chaque URL d'asset reçoit
  une empreinte `?v=…`. C'est ce qui permet à `netlify.toml` de mettre les
  assets en cache un an sans jamais servir une version périmée.
- **Images** : écrire un `<img src="…jpg">` normal avec un attribut `sizes`
  (largeur affichée, ex. `sizes="122px"` ou `sizes="(min-width: 900px) 50vw, 92vw"`).
  Le build génère les variantes AVIF / WebP / JPEG (`assets/opt/`), le
  `<picture>`, le `srcset` et les dimensions `width`/`height` (anti-CLS).
  Une nouvelle famille d'images (nouveau dossier) s'ajoute dans
  `IMAGE_WIDTHS` de `build_site.py`. Hors écran au chargement : `loading="lazy"`.
- **Polices** : Poppins et Inter sont servies depuis `assets/fonts/` (plus
  d'appel à Google Fonts). Les trois fichiers affichés en premier sont préchargés.
- **Titres et descriptions** : `<title>` de 50 à 60 caractères, meta
  description de 140 à 160 (champ `meta_description` de chaque destination).
  Le build affiche un ⚠️ si une page sort de ces bornes.
- **Données structurées** (JSON-LD) générées automatiquement : Organization,
  WebSite et FAQPage (depuis la FAQ du template) sur l'accueil ; BreadcrumbList
  et TouristTrip sur chaque séjour. L'adresse (`site.adresse`) et les réseaux
  sociaux (`site.reseaux_sociaux`) ne sont publiés que s'ils sont renseignés.

## Le simulateur ne révèle aucun prix

Le JS embarque seulement des **paliers arrondis** (1000 / 1100 / 1200 / 1350 /
1450 / 1550 €) distincts de la grille tarifaire réelle, avec une marge. Un
concurrent qui lit le code source n'obtient que des fourchettes, jamais un
prix. Aucun montant n'est affiché à l'écran : le simulateur répond uniquement
« destinations compatibles » + CTA conseiller.

## Leads (brochure / conseiller / programme)

Les formulaires écrivent dans la table Supabase `site_leads`
(projet EU `wnkakrzvtpbuovnswuel`, migration incluse :
`supabase/migrations/0006_site_leads.sql`) :

- **RLS insert-only** : le rôle `anon` peut insérer, jamais lire/modifier/supprimer.
- Consentement RGPD obligatoire (contrainte SQL + case à cocher).
- Contraintes de longueur/format sur tous les champs (anti-injection / anti-spam),
  champ honeypot côté client.
- Si Supabase est injoignable : repli automatique sur `mailto:`.

**À faire une fois** : appliquer la migration (SQL Editor du dashboard Supabase,
ou `supabase db push`). Lire les leads : dashboard → table `site_leads`
(colonne `traite` pour le suivi commercial).

## Déploiement

Site 100 % statique : uploader le contenu du dossier (sans `templates/`,
`data/`, `docs/`, `*.py`) sur n'importe quel hébergement. Penser à servir en HTTPS
(les formulaires appellent l'API Supabase en HTTPS).

Sur Netlify, `netlify.toml` gère tout : cache long des assets, `noindex` de la
brochure, page 404, redirections 301 des anciennes URL du site Framer
(`/destinations/…` → `/sejours/….html`) et blocage des fichiers de travail.
Ailleurs, reproduire ces réglages (voir `docs/audit-performance-seo.md`).

## Photos

Wikimedia Commons / NASA, licences libres — crédits générés automatiquement
dans `mentions-legales.html` depuis `assets/img/destinations/credits.json`.
Pour changer une photo : modifier la requête dans `fetch_photos.py`, supprimer
le `.jpg` concerné, relancer le script, puis `python3 build_site.py`.

# Sitos
