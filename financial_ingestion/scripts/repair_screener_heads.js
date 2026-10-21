/* Repair Screener head pointers blocked only by a shareholding parser failure.
 *
 * Usage:
 *   mongosh "mongodb://localhost:27017/financial_ingestion" --file scripts/repair_screener_heads.js
 *
 * Safety:
 * - only considers SCREENER heads whose dataset_id is null
 * - requires at least one VALID normalized fact for the candidate dataset
 * - refuses candidates with any blocking issue other than tables.shareholding/FAILED
 * - chooses the newest qualifying immutable dataset by extraction time
 */
const financialDb = db.getSiblingDB("financial_ingestion");
const snapshots = financialDb.screener_snapshots;
const facts = financialDb.financial_facts;

let inspected = 0;
let repaired = 0;
let skipped = 0;

for (const head of snapshots.find({ kind: "head", source: "SCREENER", dataset_id: null })) {
  inspected += 1;

  const candidates = snapshots.find({
    kind: "dataset",
    source: "SCREENER",
    symbol: head.symbol,
    scope: head.scope
  }).toArray().sort((a, b) => {
    const at = Date.parse(a.envelope && a.envelope.extracted_at || 0);
    const bt = Date.parse(b.envelope && b.envelope.extracted_at || 0);
    return bt - at;
  });

  let selected = null;
  for (const candidate of candidates) {
    const validFacts = facts.countDocuments({
      dataset_id: candidate.dataset_id,
      validation_status: "VALID"
    });
    if (validFacts === 0) continue;

    const issueDocs = snapshots.find({
      kind: "issues",
      dataset_id: candidate.dataset_id
    }).toArray();
    const blocking = issueDocs
      .flatMap(x => x.items || [])
      .filter(x => x.blocking === true);

    const onlyShareholdingFailure = blocking.every(
      x => x.locator === "tables.shareholding" && x.code === "FAILED"
    );
    if (!onlyShareholdingFailure) continue;

    selected = candidate;
    break;
  }

  if (!selected) {
    skipped += 1;
    print("SKIP " + head.symbol + " " + head.scope + ": no safely repairable dataset");
    continue;
  }

  const rankTime = new Date(selected.envelope.extracted_at);
  const result = snapshots.updateOne(
    { _id: head._id, dataset_id: null },
    {
      $set: {
        dataset_id: selected.dataset_id,
        rank_time: rankTime,
        content_hash: selected.envelope.content_hash,
        source_document_id: selected.envelope.source_document_id,
        publication_revision: Math.max(head.publication_revision || 0, 1)
      }
    }
  );

  if (result.modifiedCount === 1) {
    repaired += 1;
    print("REPAIRED " + head.symbol + " " + head.scope + " -> " + selected.dataset_id);
  } else {
    skipped += 1;
    print("SKIP " + head.symbol + " " + head.scope + ": head changed concurrently");
  }
}

print("");
print("Screener head repair complete");
print("Inspected: " + inspected);
print("Repaired:  " + repaired);
print("Skipped:   " + skipped);
print("Remaining null heads: " + snapshots.countDocuments({ kind: "head", source: "SCREENER", dataset_id: null }));
