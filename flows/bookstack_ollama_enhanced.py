#!/usr/bin/env python3
"""
Enhanced BookStack to FalkorDB pipeline with real Ollama Gemma3 entity extraction.
This version uses proper LLM-powered entity extraction instead of keyword matching.
"""

import os
import json
import uuid
import redis
import requests
from datetime import timedelta
from typing import List, Dict, Any
from bs4 import BeautifulSoup

import cocoindex
from cocoindex import DataScope, FlowBuilder

# FalkorDB Connection
def get_falkor_connection():
    """Get FalkorDB connection."""
    try:
        r = redis.Redis(
            host=os.environ.get('FALKOR_HOST', 'localhost'),
            port=int(os.environ.get('FALKOR_PORT', '6379')),
            decode_responses=True
        )
        r.ping()
        print(f"Connected to FalkorDB at {r.connection_pool.connection_kwargs['host']}:{r.connection_pool.connection_kwargs['port']}")
        return r
    except Exception as e:
        print(f"FalkorDB connection failed: {e}")
        return None

_FALKOR = get_falkor_connection()
_GRAPH_NAME = os.environ.get('FALKOR_GRAPH', 'graphiti_migration')

# Enhanced entity extraction with Ollama
def extract_entities_with_ollama(text: str, title: str) -> List[Dict[str, str]]:
    """Extract entities using Ollama Gemma3 12B."""
    if not text.strip():
        return []
    
    # Limit text for prompt
    text_sample = text[:1000]
    
    prompt = f"""Extract important entities from this documentation. Return JSON only.

Title: {title}
Text: {text_sample}

Find entities of these types:
- TECHNOLOGY: software, tools, frameworks, databases, platforms
- CONCEPT: methods, processes, principles, architectures
- ORGANIZATION: companies, teams, institutions
- PRODUCT: applications, services, systems

Return JSON array:
[{{"name":"Docker","type":"TECHNOLOGY","description":"Container platform"}},{{"name":"API","type":"CONCEPT","description":"Programming interface"}}]

JSON:"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma3:12b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 300
                }
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            response_text = result['response'].strip()
            
            # Extract JSON from response - be more flexible
            json_text = response_text
            
            # Handle code blocks
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                if json_end > json_start:
                    json_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                if json_end > json_start:
                    json_text = response_text[json_start:json_end].strip()
            
            # Find JSON array boundaries
            start = json_text.find('[')
            end = json_text.rfind(']') + 1
            if start >= 0 and end > start:
                json_text = json_text[start:end]
            elif not json_text.strip().startswith('['):
                print(f"Warning: No JSON array found in response: {response_text[:200]}")
                return []
            
            try:
                entities = json.loads(json_text)
                if isinstance(entities, list):
                    # Validate and clean entities
                    cleaned_entities = []
                    for entity in entities:
                        if isinstance(entity, dict) and 'name' in entity and 'type' in entity:
                            cleaned_entities.append({
                                'name': str(entity['name']).strip(),
                                'type': str(entity['type']).upper(),
                                'description': str(entity.get('description', 'Extracted entity')).strip()[:200]
                            })
                    return cleaned_entities
                else:
                    print(f"Warning: Ollama returned non-list: {entities}")
                    return []
            except json.JSONDecodeError as e:
                print(f"Warning: JSON decode error: {e}, response: {json_text[:200]}")
                return []
        else:
            print(f"Warning: Ollama API error: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"Warning: Error calling Ollama: {e}")
        return fallback_entity_extraction(text, title)

def fallback_entity_extraction(text: str, title: str) -> List[Dict[str, str]]:
    """Fallback entity extraction using keyword matching."""
    entities = []
    
    # Enhanced keyword set
    keywords = {
        # Technologies
        'docker': ('TECHNOLOGY', 'Containerization platform'),
        'kubernetes': ('TECHNOLOGY', 'Container orchestration'), 
        'redis': ('TECHNOLOGY', 'In-memory data store'),
        'postgresql': ('TECHNOLOGY', 'Relational database'),
        'falkor': ('TECHNOLOGY', 'Graph database'),
        'graphiti': ('TECHNOLOGY', 'Knowledge graph framework'),
        'bookstack': ('TECHNOLOGY', 'Documentation platform'),
        'ollama': ('TECHNOLOGY', 'Local LLM platform'),
        'neo4j': ('TECHNOLOGY', 'Graph database'),
        'python': ('TECHNOLOGY', 'Programming language'),
        'api': ('CONCEPT', 'Application Programming Interface'),
        'webhook': ('TECHNOLOGY', 'HTTP callback'),
        'github': ('TECHNOLOGY', 'Code repository'),
        'letta': ('TECHNOLOGY', 'Agent platform'),
        'huly': ('TECHNOLOGY', 'Project management'),
        'mcp': ('TECHNOLOGY', 'Model Context Protocol'),
        'claude': ('TECHNOLOGY', 'AI assistant'),
        'openai': ('TECHNOLOGY', 'AI platform'),
        'llm': ('TECHNOLOGY', 'Large Language Model'),
        'agent': ('CONCEPT', 'Autonomous software'),
        'pipeline': ('CONCEPT', 'Data processing flow'),
        'workflow': ('CONCEPT', 'Process automation'),
        'integration': ('CONCEPT', 'System connection'),
        'architecture': ('CONCEPT', 'System design'),
        'deployment': ('CONCEPT', 'System release'),
        'monitoring': ('CONCEPT', 'System observation'),
        'authentication': ('CONCEPT', 'Identity verification'),
        'authorization': ('CONCEPT', 'Access control'),
    }
    
    text_lower = text.lower()
    for keyword, (entity_type, description) in keywords.items():
        if keyword in text_lower:
            entities.append({
                'name': keyword.title(),
                'type': entity_type,
                'description': description
            })
    
    return entities

@cocoindex.op.function()
def process_page_with_enhanced_ollama(content: str) -> dict:
    """Process a BookStack page with enhanced Ollama entity extraction."""
    global _FALKOR
    
    try:
        data = json.loads(content)
        
        # Extract basic info
        page_id = str(data.get('id', 'unknown'))
        title = data.get('title', 'Untitled')
        book = data.get('book', 'Unknown')
        url = data.get('url', '')
        tags = data.get('tags', [])
        html_content = data.get('body_html', '')
        
        # Convert HTML to text
        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator="\n", strip=True)
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text_content = "\n".join(chunk for chunk in chunks if chunk)
        
        # Extract entities using Ollama
        print(f"Extracting entities for: {title[:50]}...")
        ollama_entities = extract_entities_with_ollama(text_content, title)
        
        # Add tag entities
        tag_entities = []
        for tag in tags:
            tag_entities.append({
                'name': tag,
                'type': 'TAG',
                'description': f"BookStack tag: {tag}",
                'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"tag:{tag.lower()}"))
            })
        
        # Add UUIDs to Ollama entities
        for entity in ollama_entities:
            entity['uuid'] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ent:{entity['name'].lower()}"))
        
        all_entities = ollama_entities + tag_entities
        
        # Create page info
        page_info = {
            'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, f"doc:{page_id}")),
            'page_id': page_id,
            'title': title,
            'book': book,
            'url': url,
            'content': text_content[:5000],  # Limit content
            'summary': f"BookStack documentation: {title}",
            'group_id': book.lower().replace(" ", "-").replace("_", "-"),
            'entities': all_entities
        }
        
        # Export to FalkorDB
        if _FALKOR:
            export_enhanced_to_falkor(page_info)
        
        return {
            'status': 'success',
            'entities_found': len(all_entities),
            'ollama_entities': len(ollama_entities),
            'tag_entities': len(tag_entities),
            'title': title,
            'book': book
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'title': 'Error processing page',
            'book': 'Unknown'
        }

def export_enhanced_to_falkor(page_info: dict):
    """Export enhanced page info to FalkorDB."""
    try:
        graph_name = _GRAPH_NAME
        
        # Escape single quotes in strings
        def escape_quotes(s):
            return str(s).replace("'", "\\'").replace('"', '\\"')
        
        # Create Episodic node
        episodic_query = f"""
        MERGE (d:Episodic {{uuid: '{page_info['uuid']}'}})
        SET d.name = '{escape_quotes(page_info['title'])}',
            d.content = '{escape_quotes(page_info['content'])}',
            d.summary = '{escape_quotes(page_info['summary'])}',
            d.source = 'BookStack',
            d.source_description = '{escape_quotes(page_info['book'])}',
            d.group_id = '{escape_quotes(page_info['group_id'])}',
            d.url = '{escape_quotes(page_info['url'])}',
            d.created_at = timestamp(),
            d.valid_at = timestamp()
        """
        
        _FALKOR.execute_command('GRAPH.QUERY', graph_name, episodic_query)
        
        # Create Entity nodes and MENTIONS relationships
        for entity in page_info['entities']:
            # Create entity node
            entity_query = f"""
            MERGE (e:Entity {{uuid: '{entity['uuid']}'}})
            SET e.name = '{escape_quotes(entity['name'])}',
                e.summary = '{escape_quotes(entity['description'])}',
                e.labels = ['{entity['type']}'],
                e.group_id = '{escape_quotes(page_info['group_id'])}',
                e.created_at = timestamp()
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', graph_name, entity_query)
            
            # Create MENTIONS relationship
            mentions_query = f"""
            MATCH (d:Episodic {{uuid: '{page_info['uuid']}'}})
            MATCH (e:Entity {{uuid: '{entity['uuid']}'}})
            MERGE (d)-[:MENTIONS {{
                uuid: '{str(uuid.uuid4())}',
                group_id: '{escape_quotes(page_info['group_id'])}',
                created_at: timestamp()
            }}]->(e)
            """
            
            _FALKOR.execute_command('GRAPH.QUERY', graph_name, mentions_query)
        
        print(f"Exported: {page_info['title'][:50]} with {len(page_info['entities'])} entities")
        
    except Exception as e:
        print(f"Error exporting to FalkorDB: {e}")

# Main CocoIndex Flow
@cocoindex.flow_def(name="BookStackOllamaEnhanced")
def bookstack_ollama_enhanced_flow(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    """Enhanced BookStack to FalkorDB flow with real Ollama entity extraction."""
    
    # Add source for BookStack JSON files
    data_scope["pages"] = flow_builder.add_source(
        cocoindex.sources.LocalFile(
            path="bookstack_export_full",
            included_patterns=["*.json"]
        ),
        refresh_interval=timedelta(minutes=5)
    )
    
    # Process each page
    with data_scope["pages"].row() as page:
        # Process the page with enhanced Ollama extraction
        result = page["content"].transform(process_page_with_enhanced_ollama)

if __name__ == "__main__":
    print("Enhanced BookStack to FalkorDB Flow with Ollama Gemma3")
    print("=" * 60)
    print("Features:")
    print("- Real Ollama Gemma3 12B entity extraction")
    print("- Structured entity types and descriptions")
    print("- FalkorDB direct export")
    print("- Graphiti schema compliance")
    print("\nRun with: python run_cocoindex.py update --setup flows/bookstack_ollama_enhanced.py")