"""Analytics module — association rule mining for knowledge base patterns.

Provides Apriori algorithm implementation and knowledge base transaction
extraction, enabling the Main Designer (小空) to discover:
  - Tool co-occurrence patterns (which tools are frequently used together)
  - Tag association rules (which forensic domains overlap in practice)
  - Anti-pattern correlations (which mistakes tend to co-occur)
"""

from tools.analytics.apriori import (
    generate_frequent_itemsets,
    generate_association_rules,
    format_rules_table,
)
from tools.analytics.transactions import (
    extract_transactions,
    load_all_transactions,
)
from tools.analytics.recommend import (
    recommend,
    format_recommendations,
)
