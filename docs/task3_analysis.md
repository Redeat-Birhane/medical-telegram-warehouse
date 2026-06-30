# Task 3 — Image Enrichment Analysis

## Q1: Do "promotional" posts get more views than "product_display" posts?

| Category         | Images | Avg Views | Avg Forwards |
|-------------------|--------|-----------|--------------|
| lifestyle         | 42     | 1,190.9   | 2.1          |
| promotional       | 5      | 891.4     | 4.0          |
| product_display   | 90     | 580.7     | 1.3          |
| other             | 177    | 428.2     | 1.1          |

**Finding:** No — promotional posts do not outperform product_display posts on
views (891 vs 581), though they do lead on forwards (4.0 vs 1.3). Lifestyle
posts (person, no product) actually generate the highest average views overall.

**Caveat:** the promotional sample size is very small (n=5), so this result is
not statistically reliable. The forward-count signal is more interesting:
promotional content gets shared more even though it isn't viewed the most,
suggesting it resonates differently than passive viewing metrics capture.

---

## Q2: Which channels use more visual content?

| Channel             | Total Posts | Images Detected | % With Image |
|---------------------|-------------|------------------|--------------|
| lobelia4cosmetics    | 200         | 200              | 100.0%       |
| CheMed123            | 71          | 67               | 94.4%        |
| tikvahpharma         | 200         | 47               | 23.5%        |

**Finding:** Lobelia (cosmetics) and CheMed (medical products) are
overwhelmingly visual — nearly every post includes a product image, consistent
with consumer-facing retail marketing. Tikvah Pharma is the outlier at 23.5% —
this channel posts primarily text-based pharmaceutical listings, pricing, and
catalogue information, with images reserved for higher-ticket items like
medical equipment.

---

## Q3: Image category mix per channel

| Channel             | other | product_display | lifestyle | promotional |
|---------------------|-------|------------------|-----------|-------------|
| CheMed123           | 30    | 11               | 22        | 4           |
| lobelia4cosmetics    | 112   | 71               | 16        | 1           |
| tikvahpharma         | 35    | 8                | 4         | 0           |

**Finding:** Lobelia's image strategy is dominated by product_display (71 of
200 classified images) — clean studio shots of supplement bottles, consistent
with the screenshots reviewed earlier (Nature's Bounty bottle on branded
background). CheMed shows the highest proportion of lifestyle and promotional
content relative to its size, aligning with its more brand-forward marketing
style (logo + lifestyle imagery rather than pure product shots).

---

## Q4: Top mentioned terms (product-mention proxy)

The current top-10 word frequency list — `monday`, `delivery`, `price`,
`pharmacy`, `open`, `infront`, `until`, `address`, `school`, `midnight` —
is dominated by **operational/logistics text** (store hours, location,
delivery terms) rather than actual product or drug names. This happens
because raw word-frequency counts treat boilerplate location/hours text
(repeated on nearly every post, as seen in the Lobelia images: "Infront of
Bole Medhanialem high school... Open until midnight") the same as genuine
product mentions.

**This is a known limitation, not a bug** — to truly answer "top 10 most
mentioned products/drugs" the pipeline needs either:
- a curated drug/product dictionary to filter against, or
- a basic NLP step (stopword removal + entity recognition) before counting

This is flagged as a near-term improvement in Section 4 (Next Steps).

---

## Limitations of pre-trained YOLO for domain-specific detection

1. **No pharmaceutical-specific classes.** YOLOv8's COCO-trained weights
   recognize generic objects (bottle, person, laptop) but have no concept of
   "pill bottle," "capsule blister pack," or "ultrasound probe." The
   `product_display` category is inferred from generic `bottle`/`container`
   detections, which is a coarse proxy — it can't distinguish a supplement
   bottle from a soda bottle.

2. **High "other" rate (52% of all 690 images).** Many product photos —
   especially medical equipment, branded text-heavy graphics, and pill
   capsules scattered on a table (see the CheMed yellow-background image) —
   don't match any COCO class well, so they fall into `other` by default.
   This understates true product-display volume.

3. **No text-in-image understanding.** Several images (Lobelia, Tikvah) embed
   pricing, phone numbers, and addresses directly as image text. YOLO has no
   OCR capability, so this information — arguably the most commercially
   useful part of the image — is invisible to the current pipeline.

4. **Confidence threshold tradeoffs.** A 0.3 threshold was used to balance
   recall against noise; lowering it further would increase `product_display`
   detections but also increase false positives on cluttered backgrounds.

**Recommendation for a future iteration:** fine-tune YOLO on a small labeled
set of medical/pharma product images, or add OCR (e.g. Tesseract) as a
parallel enrichment step to capture embedded pricing and contact text.