/*
 * MongoDB setup for StockAnalysis_AI financial_ingestion.
 *
 * Run with:
 *   mongosh "mongodb://localhost:27017" --file mongodb_financial_setup.js
 *
 * Recommended order:
 *   1. Run `financial-ingestion init-mongo` to seed the exact versioned mappings.
 *   2. Run this script to apply the expanded validators, indexes, and view.
 *
 * If `init-mongo` is run again later, it keeps these indexes and the view, but
 * repository.py currently reapplies its smaller validators. Re-run this script
 * afterward if you want the expanded validation rules restored.
 *
 * The script matches the immutable dataset/head model implemented by:
 *   financial_ingestion/financial_ingestion/repository.py
 *
 * It creates:
 *   - screener_snapshots
 *   - financial_filings
 *   - financial_facts
 *   - metric_definitions
 *   - ingestion_runs
 *   - current_financial_facts (read-only view)
 *
 * Ratio values are intentionally not persisted here. The last helper produces
 * ratio-ready inputs and a calculation preview for the future calculation service.
 */

const DATABASE_NAME = "financial_ingestion";
const financialDb = db.getSiblingDB(DATABASE_NAME);

function ensureCollection(name, validator) {
  const existing = financialDb.getCollectionInfos({ name });
  if (existing.length === 0) {
    financialDb.createCollection(name, {
      validator,
      validationLevel: "strict",
      validationAction: "error"
    });
    return;
  }

  if (existing[0].type === "view") {
    throw new Error(`${name} exists as a view; expected a collection`);
  }

  financialDb.runCommand({
    collMod: name,
    validator,
    validationLevel: "strict",
    validationAction: "error"
  });
}

const factValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "_id", "dataset_id", "fact_version_key", "logical_fact_key",
      "symbol", "source", "scope", "statement", "metric", "metric_label",
      "value", "unit", "period_kind", "period_type", "period_end",
      "dimensions", "dimensions_key", "source_document_id", "provenance",
      "validation_status", "mapping_version", "normalization_version",
      "schema_version", "observed_at", "created_at"
    ],
    properties: {
      _id: { bsonType: "string" },
      dataset_id: { bsonType: "string" },
      fact_version_key: { bsonType: "string" },
      logical_fact_key: { bsonType: "string" },
      symbol: { bsonType: "string" },
      source: { enum: ["SCREENER", "NSE_XBRL"] },
      scope: { enum: ["STANDALONE", "CONSOLIDATED"] },
      statement: { bsonType: "string" },
      metric: { bsonType: "string" },
      metric_label: { bsonType: "string" },
      value: { bsonType: "decimal" },
      unit: { bsonType: "string" },
      period_kind: { enum: ["INSTANT", "DURATION"] },
      period_type: {
        enum: ["INSTANT", "ANNUAL", "QUARTERLY", "HALF_YEARLY", "YTD", "TTM", "EXTENDED"]
      },
      period_start: { bsonType: ["date", "null"] },
      period_end: { bsonType: "date" },
      duration_months: { bsonType: ["int", "long", "null"] },
      dimensions: { bsonType: "array" },
      dimensions_key: { bsonType: "string" },
      source_document_id: { bsonType: "string" },
      provenance: { bsonType: "object" },
      validation_status: { enum: ["VALID"] },
      mapping_version: { bsonType: "string" },
      normalization_version: { bsonType: "string" },
      schema_version: { enum: [1] },
      observed_at: { bsonType: "date" },
      created_at: { bsonType: "date" }
    }
  }
};

const immutableDatasetValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["_id", "kind"],
    properties: {
      _id: { bsonType: "string" },
      kind: { enum: ["dataset", "head", "issues", "disclosures"] },
      symbol: { bsonType: "string" },
      source: { enum: ["SCREENER", "NSE_XBRL"] },
      scope: { enum: ["STANDALONE", "CONSOLIDATED", "UNRESOLVED"] },
      dataset_id: { bsonType: ["string", "null"] },
      envelope: { bsonType: "object" },
      items: { bsonType: "array" },
      eligible: { bsonType: "bool" },
      rank_time: { bsonType: ["date", "null"] },
      publication_revision: { bsonType: ["int", "long"] },
      created_at: { bsonType: "date" }
    }
  }
};

const metricDefinitionValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "_id", "mapping_set_version", "source", "statement", "source_label",
      "metric", "unit", "period_kind", "approved"
    ],
    properties: {
      _id: { bsonType: "string" },
      mapping_set_version: { bsonType: "string" },
      source: { enum: ["SCREENER", "NSE_XBRL"] },
      statement: { bsonType: "string" },
      source_label: { bsonType: "string" },
      metric: { bsonType: "string" },
      unit: { bsonType: "string" },
      period_kind: { enum: ["INSTANT", "DURATION"] },
      approved: { bsonType: "bool" }
    }
  }
};

const ingestionRunValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["_id", "status", "dataset_id"],
    properties: {
      _id: { bsonType: "string" },
      status: { enum: ["RECEIVED", "PROCESSING", "COMPLETED", "FAILED"] },
      dataset_id: { bsonType: "string" },
      message_id: { bsonType: "string" },
      symbol: { bsonType: "string" },
      source: { enum: ["SCREENER", "NSE_XBRL"] },
      started_at: { bsonType: "date" },
      completed_at: { bsonType: "date" },
      attempts: { bsonType: ["int", "long"] }
    }
  }
};

ensureCollection("financial_facts", factValidator);
ensureCollection("screener_snapshots", immutableDatasetValidator);
ensureCollection("financial_filings", immutableDatasetValidator);
ensureCollection("metric_definitions", metricDefinitionValidator);
ensureCollection("ingestion_runs", ingestionRunValidator);

// financial_facts: immutable identity, current dataset reads, history, and audits.
financialDb.financial_facts.createIndex(
  { fact_version_key: 1 },
  { name: "ux_fact_version_key", unique: true }
);
financialDb.financial_facts.createIndex(
  { dataset_id: 1, validation_status: 1, statement: 1, metric: 1, period_end: -1 },
  { name: "ix_dataset_statement_metric_period" }
);
financialDb.financial_facts.createIndex(
  { symbol: 1, source: 1, scope: 1, metric: 1, period_type: 1, period_end: -1 },
  { name: "ix_symbol_source_metric_period" }
);
financialDb.financial_facts.createIndex(
  { logical_fact_key: 1, observed_at: -1 },
  { name: "ix_logical_fact_history" }
);

// Head lookup and diagnostic chunk lookup. The diagnostic index is important
// because issue/disclosure chunks do not contain symbol/source/scope fields.
for (const collectionName of ["screener_snapshots", "financial_filings"]) {
  financialDb[collectionName].createIndex(
    { kind: 1, symbol: 1, source: 1, scope: 1 },
    { name: "ix_current_head" }
  );
  financialDb[collectionName].createIndex(
    { dataset_id: 1, kind: 1, _id: 1 },
    { name: "ix_dataset_diagnostics" }
  );
}

financialDb.ingestion_runs.createIndex(
  { dataset_id: 1, status: 1 },
  { name: "ix_run_dataset_status" }
);
financialDb.ingestion_runs.createIndex(
  { status: 1, started_at: -1 },
  { name: "ix_run_status_started" }
);
financialDb.ingestion_runs.createIndex(
  { message_id: 1 },
  {
    name: "ix_run_message",
    partialFilterExpression: { message_id: { $type: "string" } }
  }
);

financialDb.metric_definitions.createIndex(
  { mapping_set_version: 1, source: 1, statement: 1, source_label: 1 },
  { name: "ix_mapping_lookup" }
);
financialDb.metric_definitions.createIndex(
  { mapping_set_version: 1, metric: 1 },
  { name: "ix_mapping_metric" }
);

/*
 * Persistent read-only view containing facts from every currently selected
 * Screener and NSE XBRL head. Query this view manually or from MCP read tools.
 */
const selectedFactsViewPipeline = [
  {
    $match: {
      kind: "head",
      dataset_id: { $type: "string" }
    }
  },
  {
    $project: {
      _id: 0,
      head_id: "$_id",
      dataset_id: 1,
      rank_time: 1,
      publication_revision: 1
    }
  },
  {
    $unionWith: {
      coll: "financial_filings",
      pipeline: [
        {
          $match: {
            kind: "head",
            dataset_id: { $type: "string" }
          }
        },
        {
          $project: {
            _id: 0,
            head_id: "$_id",
            dataset_id: 1,
            rank_time: 1,
            publication_revision: 1
          }
        }
      ]
    }
  },
  {
    $lookup: {
      from: "financial_facts",
      localField: "dataset_id",
      foreignField: "dataset_id",
      as: "fact"
    }
  },
  { $unwind: "$fact" },
  {
    $replaceWith: {
      $mergeObjects: [
        "$fact",
        {
          head_id: "$head_id",
          head_rank_time: "$rank_time",
          publication_revision: "$publication_revision"
        }
      ]
    }
  }
];

const viewInfo = financialDb.getCollectionInfos({ name: "current_financial_facts" });
if (viewInfo.length === 0) {
  financialDb.createView(
    "current_financial_facts",
    "screener_snapshots",
    selectedFactsViewPipeline
  );
} else if (viewInfo[0].type === "view") {
  financialDb.runCommand({
    collMod: "current_financial_facts",
    viewOn: "screener_snapshots",
    pipeline: selectedFactsViewPipeline
  });
} else {
  throw new Error("current_financial_facts exists as a collection; expected a view");
}

function normalizeOptions(options) {
  if (!options || !options.symbol) {
    throw new Error("symbol is required");
  }
  const normalized = {
    symbol: options.symbol.trim().toUpperCase(),
    source: options.source || "SCREENER",
    scope: options.scope || "CONSOLIDATED",
    statement: options.statement,
    metric: options.metric,
    periodType: options.periodType,
    periodEndFrom: options.periodEndFrom,
    periodEndTo: options.periodEndTo,
    limit: options.limit || 500
  };
  if (!["SCREENER", "NSE_XBRL"].includes(normalized.source)) {
    throw new Error("source must be SCREENER or NSE_XBRL");
  }
  if (!["CONSOLIDATED", "STANDALONE"].includes(normalized.scope)) {
    throw new Error("scope must be CONSOLIDATED or STANDALONE");
  }
  return normalized;
}

/*
 * Optimized current-fact pipeline. It starts at the small head collection and
 * joins only the selected immutable datasets.
 *
 * Example:
 *   financialDb.screener_snapshots.aggregate(currentFactsPipeline({
 *     symbol: "TCS", statement: "profit_loss", periodType: "ANNUAL"
 *   }))
 */
function currentFactsPipeline(options) {
  const o = normalizeOptions(options);
  const factMatch = {
    validation_status: "VALID"
  };

  if (o.statement) factMatch.statement = o.statement;
  if (o.metric) factMatch.metric = o.metric;
  if (o.periodType) factMatch.period_type = o.periodType;
  if (o.periodEndFrom || o.periodEndTo) {
    factMatch.period_end = {};
    if (o.periodEndFrom) factMatch.period_end.$gte = o.periodEndFrom;
    if (o.periodEndTo) factMatch.period_end.$lte = o.periodEndTo;
  }

  return [
    {
      $match: {
        kind: "head",
        symbol: o.symbol,
        source: o.source,
        scope: o.scope,
        dataset_id: { $type: "string" }
      }
    },
    {
      $lookup: {
        from: "financial_facts",
        localField: "dataset_id",
        foreignField: "dataset_id",
        pipeline: [
          { $match: factMatch },
          { $sort: { period_end: -1, metric: 1 } },
          { $limit: o.limit }
        ],
        as: "fact"
      }
    },
    { $unwind: "$fact" },
    { $replaceWith: "$fact" },
    { $sort: { period_end: -1, statement: 1, metric: 1 } }
  ];
}

/*
 * One document per reporting period with metrics pivoted into an object.
 * Segment/dimension facts are excluded to prevent ambiguous duplicate metrics.
 *
 * Example:
 *   financialDb.screener_snapshots.aggregate(statementMatrixPipeline({
 *     symbol: "TCS", statement: "profit_loss", periodType: "ANNUAL"
 *   }))
 */
function statementMatrixPipeline(options) {
  const o = normalizeOptions(options);
  if (!o.statement) throw new Error("statement is required");
  if (o.source === "NSE_XBRL") {
    throw new Error("Use currentFactsPipeline or compareSourcesPipeline for XBRL so overlapping filing candidates remain visible");
  }

  return [
    ...currentFactsPipeline(o),
    {
      $match: {
        $expr: {
          $eq: [{ $size: { $ifNull: ["$dimensions", []] } }, 0]
        }
      }
    },
    { $sort: { observed_at: -1 } },
    {
      $group: {
        _id: {
          period_end: "$period_end",
          period_start: "$period_start",
          period_type: "$period_type",
          metric: "$metric"
        },
        value: { $first: "$value" },
        unit: { $first: "$unit" }
      }
    },
    {
      $group: {
        _id: {
          period_end: "$_id.period_end",
          period_start: "$_id.period_start",
          period_type: "$_id.period_type"
        },
        metricPairs: { $push: { k: "$_id.metric", v: "$value" } },
        unitPairs: { $push: { k: "$_id.metric", v: "$unit" } }
      }
    },
    {
      $project: {
        _id: 0,
        period_end: "$_id.period_end",
        period_start: "$_id.period_start",
        period_type: "$_id.period_type",
        metrics: { $arrayToObject: "$metricPairs" },
        units: { $arrayToObject: "$unitPairs" }
      }
    },
    { $sort: { period_end: -1 } }
  ];
}

/*
 * Compare selected Screener facts (primary) with NSE XBRL facts (reference).
 * The output keeps every source candidate; it does not silently merge
 * overlapping XBRL comparative facts or conflicts.
 *
 * Example:
 *   financialDb.current_financial_facts.aggregate(compareSourcesPipeline({
 *     symbol: "TCS", metrics: ["revenue", "net_profit"], periodType: "ANNUAL"
 *   }))
 */
function compareSourcesPipeline(options) {
  if (!options || !options.symbol) throw new Error("symbol is required");
  const match = {
    symbol: options.symbol.trim().toUpperCase(),
    scope: options.scope || "CONSOLIDATED",
    validation_status: "VALID"
  };
  if (options.periodType) match.period_type = options.periodType;
  if (options.metrics && options.metrics.length) match.metric = { $in: options.metrics };

  return [
    { $match: match },
    {
      $match: {
        $expr: {
          $eq: [{ $size: { $ifNull: ["$dimensions", []] } }, 0]
        }
      }
    },
    { $sort: { observed_at: -1 } },
    {
      $group: {
        _id: {
          metric: "$metric",
          statement: "$statement",
          unit: "$unit",
          period_start: "$period_start",
          period_end: "$period_end",
          period_type: "$period_type",
          duration_months: "$duration_months"
        },
        candidates: {
          $push: {
            source: "$source",
            value: "$value",
            dataset_id: "$dataset_id",
            source_document_id: "$source_document_id",
            fact_version_key: "$fact_version_key"
          }
        }
      }
    },
    {
      $set: {
        screener_candidates: {
          $filter: {
            input: "$candidates",
            as: "candidate",
            cond: { $eq: ["$$candidate.source", "SCREENER"] }
          }
        },
        xbrl_candidates: {
          $filter: {
            input: "$candidates",
            as: "candidate",
            cond: { $eq: ["$$candidate.source", "NSE_XBRL"] }
          }
        }
      }
    },
    {
      $project: {
        _id: 0,
        metric: "$_id.metric",
        statement: "$_id.statement",
        unit: "$_id.unit",
        period_start: "$_id.period_start",
        period_end: "$_id.period_end",
        period_type: "$_id.period_type",
        duration_months: "$_id.duration_months",
        screener_candidates: 1,
        xbrl_candidates: 1,
        comparison_status: {
          $cond: [
            {
              $and: [
                { $eq: [{ $size: "$screener_candidates" }, 1] },
                { $eq: [{ $size: "$xbrl_candidates" }, 1] }
              ]
            },
            "ONE_CANDIDATE_PER_SOURCE",
            "MISSING_OR_AMBIGUOUS"
          ]
        }
      }
    },
    { $sort: { period_end: -1, metric: 1 } }
  ];
}

/*
 * Produce a period-level input matrix for a future ratio calculation service.
 * Screener is deliberately used as the primary source, matching the platform
 * decision. Existing reported ratios such as ROCE remain visible as inputs.
 *
 * Example:
 *   financialDb.screener_snapshots.aggregate(ratioInputPipeline({
 *     symbol: "TCS", periodType: "ANNUAL"
 *   }))
 */
function ratioInputPipeline(options) {
  const o = normalizeOptions({
    ...options,
    source: "SCREENER",
    periodType: undefined,
    limit: (options && options.limit) || 5000
  });

  const durationPeriodType = (options && options.periodType) || "ANNUAL";

  const requiredMetrics = [
    "revenue", "operating_profit", "net_profit", "interest_expense",
    "borrowings", "equity_capital", "reserves", "operating_cash_flow",
    "roce", "eps"
  ];

  return [
    ...currentFactsPipeline(o),
    {
      $match: {
        metric: { $in: requiredMetrics },
        $and: [
          {
            $expr: {
              $eq: [{ $size: { $ifNull: ["$dimensions", []] } }, 0]
            }
          },
          {
            $or: [
              { period_kind: "DURATION", period_type: durationPeriodType },
              { period_kind: "INSTANT", period_type: "INSTANT" }
            ]
          }
        ]
      }
    },
    { $sort: { observed_at: -1 } },
    {
      $group: {
        _id: { period_end: "$period_end", metric: "$metric" },
        value: { $first: "$value" },
        unit: { $first: "$unit" }
      }
    },
    {
      $group: {
        _id: "$_id.period_end",
        metricPairs: { $push: { k: "$_id.metric", v: "$value" } },
        unitPairs: { $push: { k: "$_id.metric", v: "$unit" } }
      }
    },
    {
      $project: {
        _id: 0,
        symbol: { $literal: o.symbol },
        scope: { $literal: o.scope },
        source: { $literal: "SCREENER" },
        period_end: "$_id",
        inputs: { $arrayToObject: "$metricPairs" },
        units: { $arrayToObject: "$unitPairs" }
      }
    },
    { $sort: { period_end: -1 } }
  ];
}

/*
 * Preview only: calculate three ratios from ratioInputPipeline output.
 * Do not use this as the versioned persistence contract for calculated ratios.
 */
function ratioPreviewPipeline(options) {
  return [
    ...ratioInputPipeline(options),
    {
      $set: {
        calculated_preview: {
          operating_margin_percent: {
            $cond: [
              { $and: [{ $ne: ["$inputs.revenue", null] }, { $ne: ["$inputs.revenue", Decimal128("0")] }] },
              { $multiply: [{ $divide: ["$inputs.operating_profit", "$inputs.revenue"] }, Decimal128("100")] },
              null
            ]
          },
          net_profit_margin_percent: {
            $cond: [
              { $and: [{ $ne: ["$inputs.revenue", null] }, { $ne: ["$inputs.revenue", Decimal128("0")] }] },
              { $multiply: [{ $divide: ["$inputs.net_profit", "$inputs.revenue"] }, Decimal128("100")] },
              null
            ]
          },
          debt_to_equity: {
            $let: {
              vars: {
                equity: { $add: ["$inputs.equity_capital", "$inputs.reserves"] }
              },
              in: {
                $cond: [
                  { $and: [{ $ne: ["$inputs.borrowings", null] }, { $ne: ["$$equity", Decimal128("0")] }] },
                  { $divide: ["$inputs.borrowings", "$$equity"] },
                  null
                ]
              }
            }
          }
        }
      }
    }
  ];
}

// Convenient interactive API after: load("mongodb_financial_setup.js")
globalThis.F = {
  db: financialDb,
  currentFactsPipeline,
  statementMatrixPipeline,
  compareSourcesPipeline,
  ratioInputPipeline,
  ratioPreviewPipeline,
  current(options) {
    const o = normalizeOptions(options);
    const parent = o.source === "SCREENER" ? "screener_snapshots" : "financial_filings";
    return financialDb[parent].aggregate(currentFactsPipeline(o), { maxTimeMS: 30000 });
  },
  statement(options) {
    const o = normalizeOptions(options);
    const parent = o.source === "SCREENER" ? "screener_snapshots" : "financial_filings";
    return financialDb[parent].aggregate(statementMatrixPipeline(o), { maxTimeMS: 30000 });
  },
  compareSources(options) {
    return financialDb.current_financial_facts.aggregate(
      compareSourcesPipeline(options),
      { maxTimeMS: 30000 }
    );
  },
  ratioInputs(options) {
    return financialDb.screener_snapshots.aggregate(
      ratioInputPipeline(options),
      { maxTimeMS: 30000 }
    );
  },
  ratioPreview(options) {
    return financialDb.screener_snapshots.aggregate(
      ratioPreviewPipeline(options),
      { maxTimeMS: 30000 }
    );
  }
};

print(`MongoDB setup complete for database: ${DATABASE_NAME}`);
print("Collections: screener_snapshots, financial_filings, financial_facts, metric_definitions, ingestion_runs");
print("View: current_financial_facts");
print("Interactive helpers loaded as F.current, F.statement, F.compareSources, F.ratioInputs, and F.ratioPreview");
