// Read-only validation. Run with mongosh --file validation/mongodb.js.
// Change databaseName if MONGO_DATABASE differs in your environment.
(() => {
  const databaseName = "financial_ingestion";
  const financialDb = db.getSiblingDB(databaseName);
  function show(label, cursor) {
    print("\n" + label);
    cursor.forEach(row => printjson(row));
  }
  const options = {allowDiskUse: true, maxTimeMS: 60000};

  print("Database: " + databaseName);
  const collections = ["screener_snapshots", "financial_filings",
    "financial_facts", "metric_definitions", "ingestion_runs"];
  collections.forEach(name => {
    print(name + ": " + financialDb.getCollection(name).countDocuments({}));
  });

  ["screener_snapshots", "financial_filings"].forEach(name => {
    show(name + " document kinds", financialDb.getCollection(name).aggregate([
      {$group: {_id: "$kind", count: {$sum: 1}}},
      {$sort: {_id: 1}}
    ], options));
  });

  // Reporting dates and ingestion timestamps answer different questions.
  show("Fact coverage", financialDb.financial_facts.aggregate([
    {$group: {
      _id: {source: "$source", scope: "$scope", period_type: "$period_type"},
      facts: {$sum: 1},
      earliest_period: {$min: "$period_end"},
      latest_period: {$max: "$period_end"},
      latest_ingestion: {$max: "$created_at"}
    }},
    {$sort: {"_id.source": 1, "_id.period_type": 1}}
  ], options));

  // Expect zero rows. Do not treat historical datasets as duplicates.
  show("Duplicate logical facts within one dataset", financialDb.financial_facts.aggregate([
    {$group: {
      _id: {dataset_id: "$dataset_id", logical_fact_key: "$logical_fact_key"},
      copies: {$sum: 1}
    }},
    {$match: {copies: {$gt: 1}}},
    {$limit: 100}
  ], options));

  show("Missing values or invalid types (expect zero)", financialDb.financial_facts.find({
    $or: [
      {symbol: {$in: [null, ""]}},
      {dataset_id: {$in: [null, ""]}},
      {metric: {$in: [null, ""]}},
      {unit: {$in: [null, ""]}},
      {validation_status: {$ne: "VALID"}},
      {$expr: {$or: [
        {$ne: [{$type: "$value"}, "decimal"]},
        {$ne: [{$type: "$period_end"}, "date"]},
        {$ne: [{$type: "$created_at"}, "date"]}
      ]}}
    ]
  }, {
    symbol: 1, source: 1, dataset_id: 1, metric: 1, value: 1,
    unit: 1, period_end: 1, validation_status: 1
  }).limit(100));

  show("Invalid/future reporting dates", financialDb.financial_facts.find({
    $or: [
      {period_end: {$gt: new Date()}},
      {$expr: {$and: [
        {$eq: [{$type: "$period_start"}, "date"]},
        {$eq: [{$type: "$period_end"}, "date"]},
        {$gt: ["$period_start", "$period_end"]}
      ]}}
    ]
  }, {
    symbol: 1, source: 1, metric: 1,
    period_type: 1, period_start: 1, period_end: 1
  }).limit(100));

  show("Ingestion status", financialDb.ingestion_runs.aggregate([
    {$group: {
      _id: "$status", runs: {$sum: 1},
      latest_started: {$max: "$started_at"},
      latest_completed: {$max: "$completed_at"}
    }}
  ], options));
  show("Recent failed runs", financialDb.ingestion_runs.find({
    status: "FAILED"
  }).sort({started_at: -1}).limit(20));
  show("Processing longer than one hour", financialDb.ingestion_runs.find({
    status: "PROCESSING",
    started_at: {$lt: new Date(Date.now() - 60 * 60 * 1000)}
  }).limit(20));

  ["screener_snapshots", "financial_filings"].forEach(name => {
    show(name + ": selected datasets without facts",
      financialDb.getCollection(name).aggregate([
        {$match: {kind: "head", dataset_id: {$type: "string"}}},
        {$lookup: {
          from: "financial_facts",
          localField: "dataset_id", foreignField: "dataset_id",
          pipeline: [{$limit: 1}, {$project: {_id: 1}}],
          as: "facts"
        }},
        {$match: {"facts.0": {$exists: false}}},
        {$project: {symbol: 1, source: 1, scope: 1, dataset_id: 1}},
        {$limit: 50}
      ], options));
  });

  // Optional view from mongodb_financial_setup.js; do not create it here.
  if (financialDb.getCollectionInfos({name: "current_financial_facts"}).length) {
    show("Current TCS reporting periods", financialDb.current_financial_facts.aggregate([
      {$match: {symbol: "TCS"}},
      {$group: {
        _id: {source: "$source", scope: "$scope",
              period_type: "$period_type", period_end: "$period_end"},
        facts: {$sum: 1}, metrics: {$addToSet: "$metric"}
      }},
      {$sort: {"_id.period_end": -1, "_id.source": 1}}
    ], options));
  } else {
    print("SKIP: current_financial_facts view is not installed.");
  }
})();
