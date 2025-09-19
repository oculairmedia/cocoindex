#!/usr/bin/env python3
"""
Graphiti Schema Compliance Validation Script
Validates that FalkorDB data conforms to Graphiti schema specification.
"""

import os
import redis
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

class GraphitiValidator:
    """Validates FalkorDB data against Graphiti schema."""
    
    def __init__(self):
        self.falkor = redis.Redis(
            host=os.environ.get('FALKOR_HOST', 'localhost'),
            port=int(os.environ.get('FALKOR_PORT', '6379')),
            decode_responses=True
        )
        self.graph_name = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')
        self.errors = []
        self.warnings = []
    
    def query_graph(self, cypher: str) -> List[Dict]:
        """Execute Cypher query and return results."""
        try:
            result = self.falkor.execute_command('GRAPH.QUERY', self.graph_name, cypher)
            if len(result) > 1:
                return result[1]  # Skip header row
            return []
        except Exception as e:
            self.errors.append(f"Query error: {e}")
            return []
    
    def validate_episodic_nodes(self) -> Dict[str, Any]:
        """Validate Episodic nodes against Graphiti schema."""
        print("🔍 Validating Episodic nodes...")
        
        # Get all Episodic nodes
        cypher = """
        MATCH (e:Episodic)
        RETURN e.uuid, e.name, e.group_id, e.source, e.source_description, 
               e.content, e.created_at, e.valid_at
        LIMIT 100
        """
        
        nodes = self.query_graph(cypher)
        results = {
            'total_count': len(nodes),
            'missing_fields': [],
            'valid_nodes': 0,
            'sample_nodes': []
        }
        
        required_fields = ['uuid', 'name', 'group_id', 'source', 'source_description', 'content', 'created_at', 'valid_at']
        
        for node in nodes:
            node_dict = dict(zip(['uuid', 'name', 'group_id', 'source', 'source_description', 'content', 'created_at', 'valid_at'], node))
            missing = [field for field in required_fields if not node_dict.get(field)]
            
            if missing:
                results['missing_fields'].append({
                    'uuid': node_dict.get('uuid', 'unknown'),
                    'name': node_dict.get('name', 'unknown'),
                    'missing': missing
                })
            else:
                results['valid_nodes'] += 1
            
            # Add to sample
            if len(results['sample_nodes']) < 3:
                results['sample_nodes'].append(node_dict)
        
        return results
    
    def validate_entity_nodes(self) -> Dict[str, Any]:
        """Validate Entity nodes against Graphiti schema."""
        print("🔍 Validating Entity nodes...")
        
        # Get all Entity nodes
        cypher = """
        MATCH (e:Entity)
        RETURN e.uuid, e.name, e.group_id, e.summary, e.created_at, e.entity_type
        LIMIT 100
        """
        
        nodes = self.query_graph(cypher)
        results = {
            'total_count': len(nodes),
            'missing_fields': [],
            'valid_nodes': 0,
            'sample_nodes': []
        }
        
        required_fields = ['uuid', 'name', 'group_id', 'summary', 'created_at']
        
        for node in nodes:
            node_dict = dict(zip(['uuid', 'name', 'group_id', 'summary', 'created_at', 'entity_type'], node))
            missing = [field for field in required_fields if not node_dict.get(field)]
            
            if missing:
                results['missing_fields'].append({
                    'uuid': node_dict.get('uuid', 'unknown'),
                    'name': node_dict.get('name', 'unknown'),
                    'missing': missing
                })
            else:
                results['valid_nodes'] += 1
            
            # Add to sample
            if len(results['sample_nodes']) < 3:
                results['sample_nodes'].append(node_dict)
        
        return results
    
    def validate_mentions_relationships(self) -> Dict[str, Any]:
        """Validate MENTIONS relationships against Graphiti schema."""
        print("🔍 Validating MENTIONS relationships...")
        
        cypher = """
        MATCH (ep:Episodic)-[r:MENTIONS]->(ent:Entity)
        RETURN r.uuid, r.created_at, r.group_id, ep.name, ent.name
        LIMIT 50
        """
        
        rels = self.query_graph(cypher)
        results = {
            'total_count': len(rels),
            'missing_fields': [],
            'valid_relationships': 0,
            'sample_relationships': []
        }
        
        required_fields = ['uuid', 'created_at']
        
        for rel in rels:
            rel_dict = dict(zip(['uuid', 'created_at', 'group_id', 'episodic_name', 'entity_name'], rel))
            missing = [field for field in required_fields if not rel_dict.get(field)]
            
            if missing:
                results['missing_fields'].append({
                    'episodic': rel_dict.get('episodic_name', 'unknown'),
                    'entity': rel_dict.get('entity_name', 'unknown'),
                    'missing': missing
                })
            else:
                results['valid_relationships'] += 1
            
            # Add to sample
            if len(results['sample_relationships']) < 3:
                results['sample_relationships'].append(rel_dict)
        
        return results
    
    def validate_relates_to_relationships(self) -> Dict[str, Any]:
        """Validate RELATES_TO relationships against Graphiti schema."""
        print("🔍 Validating RELATES_TO relationships...")
        
        cypher = """
        MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity)
        RETURN r.uuid, r.created_at, r.group_id, r.predicate, r.fact, e1.name, e2.name
        LIMIT 50
        """
        
        rels = self.query_graph(cypher)
        results = {
            'total_count': len(rels),
            'missing_fields': [],
            'valid_relationships': 0,
            'sample_relationships': []
        }
        
        required_fields = ['uuid', 'created_at']
        
        for rel in rels:
            rel_dict = dict(zip(['uuid', 'created_at', 'group_id', 'predicate', 'fact', 'subject_name', 'object_name'], rel))
            missing = [field for field in required_fields if not rel_dict.get(field)]
            
            if missing:
                results['missing_fields'].append({
                    'subject': rel_dict.get('subject_name', 'unknown'),
                    'object': rel_dict.get('object_name', 'unknown'),
                    'missing': missing
                })
            else:
                results['valid_relationships'] += 1
            
            # Add to sample
            if len(results['sample_relationships']) < 3:
                results['sample_relationships'].append(rel_dict)
        
        return results
    
    def validate_uuid_uniqueness(self) -> Dict[str, Any]:
        """Validate UUID uniqueness across all nodes."""
        print("🔍 Validating UUID uniqueness...")
        
        cypher = """
        MATCH (n)
        WHERE exists(n.uuid)
        RETURN n.uuid, labels(n)[0] as node_type
        """
        
        nodes = self.query_graph(cypher)
        uuid_counts = {}
        
        for node in nodes:
            uuid_val, node_type = node
            if uuid_val in uuid_counts:
                uuid_counts[uuid_val].append(node_type)
            else:
                uuid_counts[uuid_val] = [node_type]
        
        duplicates = {uuid_val: types for uuid_val, types in uuid_counts.items() if len(types) > 1}
        
        return {
            'total_uuids': len(uuid_counts),
            'duplicate_uuids': len(duplicates),
            'duplicates': duplicates
        }
    
    def validate_group_id_consistency(self) -> Dict[str, Any]:
        """Validate group_id consistency."""
        print("🔍 Validating group_id consistency...")
        
        cypher = """
        MATCH (n)
        WHERE exists(n.group_id)
        RETURN DISTINCT n.group_id, count(n) as node_count
        ORDER BY node_count DESC
        """
        
        groups = self.query_graph(cypher)
        
        return {
            'total_groups': len(groups),
            'groups': [{'group_id': group[0], 'node_count': group[1]} for group in groups]
        }
    
    def run_full_validation(self) -> Dict[str, Any]:
        """Run complete Graphiti schema validation."""
        print("🚀 Starting Graphiti Schema Compliance Validation")
        print("=" * 60)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'graph_name': self.graph_name,
            'episodic_validation': self.validate_episodic_nodes(),
            'entity_validation': self.validate_entity_nodes(),
            'mentions_validation': self.validate_mentions_relationships(),
            'relates_to_validation': self.validate_relates_to_relationships(),
            'uuid_validation': self.validate_uuid_uniqueness(),
            'group_id_validation': self.validate_group_id_consistency(),
            'errors': self.errors,
            'warnings': self.warnings
        }
        
        return results
    
    def print_validation_report(self, results: Dict[str, Any]):
        """Print formatted validation report."""
        print("\n📊 VALIDATION REPORT")
        print("=" * 60)
        
        # Episodic nodes
        ep = results['episodic_validation']
        print(f"📄 Episodic Nodes: {ep['valid_nodes']}/{ep['total_count']} valid")
        if ep['missing_fields']:
            print(f"   ❌ {len(ep['missing_fields'])} nodes missing required fields")
        
        # Entity nodes
        ent = results['entity_validation']
        print(f"🏷️  Entity Nodes: {ent['valid_nodes']}/{ent['total_count']} valid")
        if ent['missing_fields']:
            print(f"   ❌ {len(ent['missing_fields'])} nodes missing required fields")
        
        # MENTIONS relationships
        men = results['mentions_validation']
        print(f"🔗 MENTIONS Relationships: {men['valid_relationships']}/{men['total_count']} valid")
        if men['missing_fields']:
            print(f"   ❌ {len(men['missing_fields'])} relationships missing required fields")
        
        # RELATES_TO relationships
        rel = results['relates_to_validation']
        print(f"🔗 RELATES_TO Relationships: {rel['valid_relationships']}/{rel['total_count']} valid")
        if rel['missing_fields']:
            print(f"   ❌ {len(rel['missing_fields'])} relationships missing required fields")
        
        # UUID uniqueness
        uuid_val = results['uuid_validation']
        print(f"🆔 UUID Uniqueness: {uuid_val['total_uuids']} total, {uuid_val['duplicate_uuids']} duplicates")
        
        # Group IDs
        group_val = results['group_id_validation']
        print(f"🏢 Group IDs: {group_val['total_groups']} distinct groups")
        
        # Overall compliance
        total_issues = (
            len(ep['missing_fields']) + 
            len(ent['missing_fields']) + 
            len(men['missing_fields']) + 
            len(rel['missing_fields']) + 
            uuid_val['duplicate_uuids']
        )
        
        if total_issues == 0:
            print("\n✅ GRAPHITI SCHEMA COMPLIANCE: PASSED")
        else:
            print(f"\n❌ GRAPHITI SCHEMA COMPLIANCE: FAILED ({total_issues} issues)")
        
        print("=" * 60)

def main():
    """Main validation function."""
    validator = GraphitiValidator()
    
    try:
        results = validator.run_full_validation()
        validator.print_validation_report(results)
        
        # Save detailed results
        with open('graphiti_validation_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📁 Detailed results saved to: graphiti_validation_results.json")
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")

if __name__ == "__main__":
    main()
