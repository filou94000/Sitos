# Audit performance & SEO — site Learning Trip

Date : 30 septembre 2026 · Périmètre : dépôt `Sitos` (site statique généré par `build_site.py`).
Contrainte respectée : **design, textes éditoriaux et fonctionnalités inchangés**.
Seuls les balises `<title>`, les meta descriptions et quelques balises sémantiques ont été modifiés (§ 3, tout est signalé).

---

## 0. Résultats en bref

| Mesure | Avant | Après |
|---|---|---|
| Accueil — poids téléchargé au premier affichage (mobile) | **5,2 Mo** | **1,0 Mo** (dont 0,85 Mo de vidéo d'en-tête inchangée) |
| Accueil — poids de la page entière parcourue (mobile / ordinateur) | 11,4 Mo | 2,5 Mo / 1,5 Mo |
| Page séjour Montréal — premier affichage / page entière (mobile) | 579 Ko / 3,5 Mo | 196 Ko / 0,7 Mo |
| Page séjour Tanger — premier affichage / page entière (mobile) | 791 Ko / 2,2 Mo | 265 Ko / 0,56 Mo |
| Requêtes au premier affichage (accueil) | 21 | 13 |
| Requêtes vers des services tiers au chargement | 2 (Google Fonts, YouTube) | **0** |
| LCP accueil (mobile, 4G lente simulée) | 0,79 s | **0,42 s** (élément LCP : le titre `<h1>`) |
| LCP page séjour Montréal (idem) | 3,84 s (au-dessus de la cible de 2,5 s) | **1,10 s** |
| LCP page séjour Tanger (idem) | 4,92 s (zone « mauvais » au-delà de 4 s) | **1,28 s** |
| CLS (toutes pages mesurées) | ≤ 0,001 | ≤ 0,001 (cible < 0,1) |
| JavaScript de l'accueil (INP : moins de code à exécuter, rien de bloquant) | 55 Ko, synchrone, dont 32 Ko de code mort | 14 Ko, minifié, différé (`defer`) |
| Balises `<title>` dans la cible 50–60 car. | 0 / 12 | 12 / 12 |
| Meta descriptions dans la cible 140–160 car. | 0 / 12 | 12 / 12 |
| Données structurées (JSON-LD) | aucune | Organization, WebSite, FAQPage, BreadcrumbList, TouristTrip |

**Méthode.** Poids : simulation du choix d'image du navigateur (`srcset`/`sizes`, navigateur récent qui lit l'AVIF), fichiers texte comptés compressés (gzip). Core Web Vitals : Chrome 154 headless, profil mobile de Lighthouse (412 × 915 px, CPU ralenti ×4, 4G lente : 150 ms de latence, 1,6 Mb/s), médiane de 3 chargements à froid, serveur local compressé. Ces chiffres de laboratoire sont optimistes par rapport au terrain (pas de DNS/TLS vers l'hébergeur) ; les données réelles viendront de Search Console (§ 4).
**Design.** Captures pleine page avant/après (1440 px et 390 px, accueil, Montréal, Tanger, mentions légales), comparées pixel à pixel : mêmes hauteurs de page au pixel près, écarts limités au bruit de compression des photos (0,02 % à 1,7 % des pixels), seule différence visible : la zone vidéo affiche désormais la vignette YouTube avant le clic (§ 1, point P8).
**Fonctionnalités testées** : modales (rappel, brochure, programme), simulateur (budget, priorités), filtres de destinations, FAQ, menu mobile, barre de progression, bouton son, lecture vidéo, page 404. Les formulaires n'ont pas été soumis (ils écrivent dans la vraie base Supabase).

---

## 1. Rapport d'audit — état initial

### Performance

| # | Impact | Problème | Où | Correction |
|---|---|---|---|---|
| P1 | **Élevé** | Images surdimensionnées, au format JPEG/PNG uniquement : photos de destinations en 1800 px (229 à 703 Ko) affichées en cartes de ~376 px, en vignettes de 86 px (simulateur) et en fonds de 250 px ; photos équipe 560 px pour un rond de 122 px ; aucune variante WebP/AVIF, aucun `srcset`. | `build_site.py` (`dest_card`, `gallery_block`, `referent_block`), `templates/index.html`, `assets/js/destinations.js` | Le build génère des variantes AVIF / WebP / JPEG aux largeurs utiles (`assets/opt/`), et transforme chaque `<img>` en `<picture>` avec `srcset`/`sizes`. |
| P2 | **Élevé** | Musique d'ambiance en `preload="auto"` : 3,4 Mo téléchargés dès l'arrivée, alors que les navigateurs bloquent la lecture automatique avec son. | `templates/index.html` (balise `<audio>`) | `preload="none"` : le fichier n'est chargé qu'au lancement de la lecture (même comportement). |
| P3 | **Élevé** | Pile « brochure » : deux photos 1800 px en fond CSS (466 + 230 Ko) chargées au démarrage pour des vignettes de 250 × 350 px ; couverture (102 Ko) et logos partenaires (72 Ko) sans chargement différé. | `templates/index.html`, sections Brochure et Partenaires | Fonds en `image-set()` AVIF/WebP 800 px (49 + 16 Ko), `loading="lazy"` sur les images hors écran. |
| P4 | **Élevé** | Rendu bloqué par deux feuilles de style : `site.css` (46 Ko non minifiés) et la CSS Google Fonts, sur un domaine tiers (2 connexions supplémentaires : fonts.googleapis.com puis fonts.gstatic.com). | `<head>` de tous les templates | CSS minifié, **réduit aux règles utilisées par chaque page** et intégré dans la page (5 à 7 Ko compressés) ; polices auto-hébergées. |
| P5 | **Élevé** | Image LCP des pages séjour : photo 1800 px JPEG (jusqu'à 703 Ko) sans priorité de chargement. | `templates/sejour.html` | Variante AVIF adaptée à l'écran + `fetchpriority="high"`. Accueil : l'affiche de la vidéo est préchargée en priorité haute. |
| P6 | Moyen | Code mort : `land.js` (32 Ko) et ~190 lignes de globe 3D dans `site.js`, chargés alors qu'aucune page ne contient le `<canvas id="globe">`. | `templates/index.html`, `assets/js/site.js` | Supprimés (`land.js`, `gen_landmask.py`, `initGlobe`). |
| P7 | Moyen | Scripts synchrones et non minifiés ; `destinations.js` chargé sur les pages séjour qui n'en ont pas besoin. | fin de `<body>` des templates | `defer`, `site.min.js` (10 Ko au lieu de 20 + 32), `destinations.js` seulement sur l'accueil, `config.js` retiré de la page légale. |
| P8 | Moyen | Lecteur YouTube (iframe tierce, plusieurs centaines de Ko de JS) chargé dès qu'on approche de la section vidéo. | `templates/index.html`, section Vidéo | Façade : vignette + bouton lecture, le lecteur n'est chargé qu'au clic (lecture automatique). Sans JS, le lien ouvre YouTube. Cohérent avec la mention « ni cookie de suivi » des mentions légales. |
| P9 | Moyen | Aucune dimension intrinsèque (`width`/`height`) sur les images. | toutes les pages | Ajoutées automatiquement par le build (+ `img { height: auto }`). |
| P10 | Moyen | Pas de politique de cache (Netlify revalide tout à chaque visite) ni d'empreinte sur les fichiers. | `netlify.toml` | Empreinte `?v=…` sur chaque URL d'asset, `Cache-Control: max-age=31536000, immutable`. |
| P11 | Moyen | Barre de progression : `scrollHeight` relu à chaque événement de défilement (recalcul de mise en page forcé) et animation de `width`. | `assets/js/site.js`, `site.css` | Mise à jour une fois par image (`requestAnimationFrame`), hauteur mise en cache, animation en `transform: scaleX()`. |
| P12 | Faible | `will-change: transform` sur tous les boutons, `preserve-3d` + `perspective` sur les 11 cartes : couches GPU inutiles. | `assets/css/site.css` | Supprimés (aucun effet visuel). |
| P13 | Faible | Changement de police (`swap`) sans police de secours calibrée : léger décalage du texte à l'arrivée des polices. | CSS | Polices de secours « Poppins Fallback » / « Inter Fallback » dont les métriques ont été mesurées (`size-adjust`, `ascent-override`…). |
| P14 | Faible | CSS inutilisé (`.section-dark`, `.partner(s)`…) et règles propres à une seule page servies partout. | `site.css` | Élagage automatique page par page au build. |
| P15 | Faible | Vidéo d'en-tête (848 Ko) et MP3 (3,4 Mo) non réencodés. | `assets/` | Hors code (pas d'outil vidéo sur la machine) : voir § 4. |
| P16 | Faible | Compteurs du hero écrits « 0 » dans le HTML (visibles ainsi sans JavaScript et par certains robots). | `templates/index.html` | Non modifié (comportement voulu) : voir § 4. |

### SEO

| # | Impact | Problème | Où | Correction |
|---|---|---|---|---|
| S1 | **Élevé** | Le site en ligne (Framer) a d'autres URL (`/destinations/montreal`, `/politique-de-confidentialité`…). Sans redirection, la mise en ligne ferait perdre le référencement acquis et casserait les liens existants. | hébergement | 17 redirections 301 dans `netlify.toml` (liste relevée dans le sitemap Framer du 30/09/2026). |
| S2 | **Élevé** | Meta descriptions trop longues sur toutes les pages (162 à 205 car., tronquées dans Google) ; titre de l'accueil trop long (73 car.) ; titres séjour trop courts (42 à 49 car.). | `templates/index.html`, `data/destinations.json`, `templates/sejour.html` | Réécrits dans les cibles (50–60 / 140–160). Le build signale toute page hors cible. |
| S3 | **Élevé** | Aucune donnée structurée schema.org. | toutes les pages | JSON-LD généré : Organization + WebSite + FAQPage (accueil), BreadcrumbList + TouristTrip (séjours). |
| S4 | **Élevé** | `robots.txt` interdit `mentions-legales.html`, qui porte déjà un `noindex` : Google ne peut pas lire ce `noindex` et peut indexer l'URL sans contenu. | `robots.txt` | Interdiction retirée (le `noindex` suffit) ; `robots.txt` généré par le build. |
| S5 | **Élevé** | Pas de page 404 : `netlify.toml` renvoyait le contenu de l'accueil avec un statut 404 (contenu dupliqué, « soft 404 »). | `netlify.toml` | Vraie page `404.html` (noindex, liens vers l'accueil et 3 séjours), servie aussi par `serve.py` en local. |
| S6 | Moyen | Open Graph incomplet (pas de `og:site_name`, `og:locale`, dimensions ni texte alternatif de l'image) ; pas de Twitter Cards ; image de partage des séjours en JPEG 1800 px. | `<head>` | Balises complétées ; image de partage des séjours en JPEG 1200 px avec dimensions. |
| S7 | Moyen | Sémantique : pas de `<main>` sur les pages séjour et légale ; le hero (et donc le `<h1>`) hors du `<main>` de l'accueil ; menu sans `<nav>` ; fil d'Ariane en simple paragraphe. | templates | `<main>` englobant, `<nav aria-label>` pour le menu et le fil d'Ariane (`aria-current`). |
| S8 | Moyen | Liens internes vers `index.html` alors que l'URL canonique est `/` : deux URL pour la même page. | templates | Liens vers `./` et `../`. |
| S9 | Moyen | Brochure PDF « contre formulaire » indexable (son URL figure dans le JS) ; gabarit `brochure.html` public. | `assets/brochure/` | En-tête `X-Robots-Tag: noindex` (`netlify.toml`) + meta `noindex` sur le gabarit. |
| S10 | Moyen | Netlify publie tout le dépôt : gabarits (avec `{{VILLE}}`), `data/`, scripts Python, README accessibles publiquement. | `netlify.toml` | Ces chemins renvoient désormais une 404. |
| S11 | Moyen | Sitemap sans `<lastmod>`. | `sitemap.xml` | `lastmod` = date du dernier changement réel du contenu (empreinte stockée dans `data/sitemap-state.json`). |
| S12 | Moyen | Ni manifest, ni icônes 192/512 ; favicon sans taille déclarée. | `<head>` | `site.webmanifest` + `icon-192.png` / `icon-512.png` (redessinées d'après l'icône « LT »). |
| S13 | Faible | Hiérarchie des titres : `<h4>` du pied de page juste après des `<h2>` (niveau sauté). | pied de page | Remplacés par `<p class="footer-title">` au rendu identique. |
| S14 | — | Points conformes, rien à changer : un seul `<h1>` par page, `lang="fr"`, `viewport`, canonical, textes `alt` présents et descriptifs, URL lisibles (`/sejours/montreal.html`), ancres explicites. `hreflang` sans objet (site 100 % en français). | | |

---

## 2. Ce qu'il faut savoir pour faire évoluer le site

- **Toujours relancer `python3 build_site.py`** après une modification de template, de `site.css`, de `site.js` ou d'une image : CSS inliné, JS minifié, variantes d'images et empreintes `?v=` en dépendent.
- **Nouvelle image** : un `<img src="…">` normal avec un attribut `sizes` (ex. `sizes="122px"`) ; le build fait le reste. Nouveau dossier d'images : l'ajouter à `IMAGE_WIDTHS` dans `build_site.py`.
- **Nouvelle page** : copier le `<head>` d'un template (`{{HEAD_ASSETS}}`), passer la page dans `finalize()` et l'ajouter à `PAGES` pour le sitemap.
- Le build affiche un ⚠️ si un titre ou une description sort des cibles, ou si une image n'a pas de `sizes`.

---

## 3. Récapitulatif des changements, fichier par fichier

**Textes modifiés (signalés, autorisés par la consigne)** : `<title>` de l'accueil (« Séjours pédagogiques à l'étranger pour CFA · Learning Trip ») et des 11 séjours (ville + pays quand la longueur le permet) ; les 12 meta descriptions raccourcies ; nouvelles balises `og:image:alt` / `twitter:*` ; titres du pied de page passés de `<h4>` à `<p>` (même texte, même rendu). Nouvelle page 404 (textes nouveaux). Aucun texte visible des pages existantes n'a changé.

| Fichier | Changements |
|---|---|
| `build_site.py` | Pipeline d'images (variantes AVIF/WebP/JPEG, `<picture>`, `srcset`/`sizes`, `width`/`height`, `decoding="async"`, fonds `image-set()`, nettoyage des variantes orphelines) ; CSS minifié, élagué par page et inliné ; polices préchargées ; minification de `site.js` ; empreintes `?v=` ; JSON-LD ; titres SEO calculés ; image de partage 1200 px ; contrôle des longueurs titre/description/h1 ; page 404 ; manifest ; sitemap avec `lastmod` ; `robots.txt`. AVIF désactivé automatiquement si la version de Pillow ne le gère pas. |
| `templates/index.html` | `<head>` (titre, description, OG complet, Twitter Cards, manifest, préchargement de l'affiche vidéo, `{{HEAD_ASSETS}}`, `{{JSONLD}}`) ; `<main>` englobe le hero ; `<nav>` ; liens `./` ; `sizes` et `loading="lazy"` sur les images ; façade YouTube ; `<audio preload="none">` ; titres du pied de page ; scripts `defer`, `land.js` retiré. |
| `templates/sejour.html` | `<head>` (titre `{{SEO_TITLE}}`, OG/Twitter avec image 1200 px, JSON-LD) ; `<main>` ; `<nav>` menu + fil d'Ariane ; image LCP `fetchpriority="high"` + `sizes="100vw"` ; liens `../` ; scripts `defer`, `destinations.js` retiré. |
| `templates/legal.html` | Polices locales + CSS inliné, `<main>`, `<nav>`, liens `./`, seul `site.min.js` chargé. `noindex` conservé. **Éditeur complété** avec l'identité légale publiée dans les CGV du site en ligne (Learning Trip FZE, licence, siège, dirigeant), directeur de la publication, responsable du traitement ; hébergeur à compléter à la mise en ligne. Lien vers les CGV. |
| `templates/404.html` | **Nouveau** : page 404 (chemins absolus, `noindex`). |
| `templates/cgv.html` → `cgv.html` | **Nouveau** : conditions générales de vente reprises mot pour mot de https://www.learningtrip.fr/cgv (12 articles numérotés, 1 097 mots identiques ; seules 4 phrases coupées en deux paragraphes sur la page Framer ont été recollées). `noindex`, liée depuis le pied de page de toutes les pages. |
| `templates/brochure.html` | `<meta name="robots" content="noindex">`. |
| `assets/css/site.css` | Polices de secours dans `--font-title`/`--font-body` ; `img { height: auto }` ; `picture` transparent pour la mise en page ; barre de progression en `transform` ; suppression de `will-change` (boutons) et `preserve-3d`/`perspective` (cartes) ; `.footer-title` ; styles de la façade vidéo. |
| `assets/css/fonts.css` | **Nouveau** : `@font-face` Poppins 500/600/700 et Inter (variable), `font-display: swap`, découpage par alphabet (`unicode-range`), polices de secours calibrées. |
| `assets/fonts/` | **Nouveau** : 9 fichiers woff2 (192 Ko au total, le navigateur n'en charge que 4 en pratique), fichiers d'origine Google Fonts, licence SIL OFL 1.1. |
| `assets/js/site.js` | Globe 3D supprimé ; barre de progression optimisée ; façade YouTube (`initVideoFacade`). |
| `assets/js/site.min.js` | **Généré** (10 Ko). |
| `assets/js/destinations.js` | **Généré** : vignettes du simulateur en 240 px. |
| `assets/js/land.js`, `gen_landmask.py` | **Supprimés** (globe inutilisé, récupérables dans l'historique git). |
| `assets/opt/` | **Généré** : 405 variantes d'images (18 Mo, servies seulement à la taille utile). |
| `assets/img/icon-192.png`, `icon-512.png` | **Nouveaux** : icônes du manifest. |
| `data/destinations.json` | 11 meta descriptions raccourcies ; `site.description`, `site.reseaux_sociaux` (vide), `site.raison_sociale` et `site.adresse` (siège de Fujairah, repris des CGV en ligne) publiés dans le JSON-LD (`legalName`, `address`). |
| `data/sitemap-state.json` | **Généré** : empreinte + date de dernière modification de chaque page. |
| `index.html`, `sejours/*.html`, `mentions-legales.html`, `404.html`, `sitemap.xml`, `robots.txt`, `site.webmanifest` | **Régénérés** par le build. |
| `netlify.toml` | 301 depuis les URL Framer (dont `/cgv` → `/cgv.html`) ; 404 forcée pour les fichiers internes ; suppression de la règle « tout → accueil » ; cache long des assets ; `X-Robots-Tag: noindex` sur la brochure. |
| `serve.py` | Sert `404.html` pour les URL inconnues (comme Netlify). |
| `requirements.txt` | Pillow ≥ 11.2 (AVIF). |
| `README.md` | Structure à jour, règles de build performance/SEO, déploiement. |

---

## 4. Actions hors code

### À faire avant ou au moment de la mise en ligne
1. **Décider de la bascule Framer → ce site.** Aujourd'hui learningtrip.fr est servi par Framer : rien de ce dépôt n'est en ligne. Il faut déployer ce dossier (Netlify est déjà configuré), puis faire pointer le domaine vers le nouvel hébergement (accès au registrar du domaine nécessaire).
2. ~~**Valider les redirections des destinations disparues**~~ : validé le 30/09/2026. `/destinations/agadir` et `/destinations/marrakech` → Tanger, `/destinations/le-quebec` → Montréal (`netlify.toml`).
3. ~~**Page CGV**~~ : fait le 30/09/2026 (`cgv.html`, reprise de la page Framer, redirection `/cgv`).
4. **Mentions légales** : le site Framer n'a pas de page « Mentions légales ». L'éditeur a été complété avec l'identité publiée à l'article 1 des CGV en ligne ; décisions du 30/09/2026 : directeur de la publication **Raoul Dey**, siège **Dubaï**. Reste à faire : **hébergeur** (dépend de la mise en ligne, le build le signale tant qu'il manque) ; **CGV à vérifier** : reprises telles quelles, elles indiquent un siège à Fujairah (Twin Towers, P.O. Box 4422), cohérent avec une licence de zone franche. Si le siège légal est bien Dubaï, corriger aussi les CGV (ici et sur le site Framer).
5. **Supabase** : `assets/js/config.js` pointe vers le projet Supabase de Rayan (conservé pour l'instant, décision du 30/09/2026). Tant que ce n'est pas changé, les demandes de contact arrivent chez lui.
6. **Netlify** : domaine principal `www.learningtrip.fr` (redirection automatique de `learningtrip.fr`), HTTPS forcé. Vérifier que l'option **Pretty URLs** est désactivée : sinon Netlify redirige `/sejours/montreal.html` vers `/sejours/montreal` et les URL canoniques ne correspondent plus.
7. **Réduire ce que Netlify publie** : tout le dépôt est publié, y compris `assets/brochure/Img_Alumni_Canada/` (107 Mo de photos non utilisées par le site), `assets/videoplayback.mp4` (9,6 Mo), des PNG sources (`assets/Ernesto.png`, `Hamza.png`, `img/referents/*.png`, `img/referents.png`) et un MP3 non utilisé. Les déplacer hors du dépôt, ou publier un dossier `dist/` qui ne contient que le site.

### Juste après la mise en ligne
8. **Google Search Console** : vérifier le domaine, soumettre `https://www.learningtrip.fr/sitemap.xml`, contrôler l'indexation et les redirections (rapport « Pages »), puis suivre les Core Web Vitals réels (rapport « Signaux Web essentiels »).
9. **Tester les données structurées** avec le test des résultats enrichis de Google, sur l'accueil et une page séjour. La FAQ est balisée, mais Google n'affiche plus ces extraits que pour quelques sites (santé, administration) : le balisage reste utile aux autres moteurs et aux assistants IA.
10. **Tester le partage** (LinkedIn Post Inspector, Facebook Sharing Debugger) pour vider le cache des anciennes images de partage.
11. **Bing Webmaster Tools** : importer le site depuis Search Console.

### Contenu et informations manquantes (placeholders)
12. ~~**Adresse du siège**~~ : Dubaï (décision du 30/09/2026), publiée dans le JSON-LD (ville et pays). Une fiche Google Business Profile n'a de sens qu'avec une adresse qui reçoit du public.
13. **Réseaux sociaux** (page LinkedIn de Learning Trip, Instagram…) → `site.reseaux_sociaux` (propriété `sameAs` du JSON-LD).
14. **Incohérences de chiffres à arbitrer** (textes non modifiés, par consigne) : l'accueil annonce « 350+ apprentis » et « 99 % de satisfaction », la brochure PDF « 150+ » et « 100 % » ; la FAQ dit « un conseiller vous répond en 30 minutes », les boutons « sous 24 h ouvrées » ; la FAQ parle d'« une à deux semaines », la brochure d'« une semaine ».
15. ~~**Deux politiques de confidentialité différentes**~~ : décision du 30/09/2026, on garde celle du nouveau site (Supabase en Irlande, aucun cookie de suivi, **conservation 24 mois**). La page Framer (OVH, Google Analytics, 3 à 5 ans) disparaîtra à la bascule, redirigée vers les mentions légales.
16. **Compteurs du hero** : le HTML contient « 0 » que le JavaScript anime jusqu'à la valeur finale. Sans JavaScript, et pour certains robots, les chiffres restent à 0. Si ces chiffres comptent pour le référencement, écrire la valeur finale dans le HTML et partir de 0 seulement au moment de l'animation (léger changement de comportement, donc non fait).

### Médias (outil vidéo nécessaire, non disponible ici)
17. **Vidéo d'en-tête** (848 Ko, désormais le plus gros fichier du premier affichage) : proposer une version mobile plus légère (≈ 720 px, 400–500 Ko) et une version WebM/AV1, par exemple avec `ffmpeg -i hero-loop.mp4 -vf scale=720:-2 -c:v libx264 -crf 28 -preset slow -an hero-loop-720.mp4`.
18. **Musique** (3,4 Mo) : la réencoder en 96 kb/s, soit environ 1,5 Mo (`ffmpeg -i ambiance-instrumental.mp3 -b:a 96k ambiance-96k.mp3`). Elle n'est plus téléchargée qu'à la lecture, mais le gain reste utile sur mobile.

### Si le site est hébergé ailleurs que sur Netlify
Netlify compresse automatiquement (Brotli/gzip) et applique `netlify.toml`. Ailleurs, reproduire les règles suivantes.

Apache (`.htaccess`) :
```apache
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/css application/javascript application/json image/svg+xml application/manifest+json
</IfModule>
<IfModule mod_headers.c>
  <FilesMatch "\.(avif|webp|jpe?g|png|woff2|js|css|mp4|mp3)$">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </FilesMatch>
  <FilesMatch "\.html$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
  <If "%{REQUEST_URI} =~ m#^/assets/brochure/#">
    Header set X-Robots-Tag "noindex"
  </If>
</IfModule>
ErrorDocument 404 /404.html
Redirect 301 /destinations/montreal /sejours/montreal.html
# … mêmes redirections que netlify.toml
```

Nginx :
```nginx
gzip on; gzip_types text/css application/javascript application/json image/svg+xml application/manifest+json;
# brotli on; brotli_types …;   (si le module ngx_brotli est installé)
location ~* \.(avif|webp|jpe?g|png|woff2|js|css|mp4|mp3)$ { add_header Cache-Control "public, max-age=31536000, immutable"; }
location /assets/brochure/ { add_header X-Robots-Tag "noindex"; }
error_page 404 /404.html;
location = /destinations/montreal { return 301 /sejours/montreal.html; }
# … mêmes redirections que netlify.toml
```
