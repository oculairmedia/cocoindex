# Ollama Integration Master Guide
## Advanced Entity Extraction for Enhanced BookStack Pipeline

### 🎯 **Objective**
Integrate Ollama-powered advanced entity extraction into the production `flows/bookstack_enhanced_localhost.py` pipeline to replace mock entity extraction with real LLM-powered analysis.

---

## 📋 **Current Pipeline Overview**

### **Production Pipeline**: `flows/bookstack_enhanced_localhost.py`
- ✅ **Status**: Operational with 154 documents processed
- ✅ **Mock Extraction**: Simple keyword-based entity extraction
- ✅ **FalkorDB Integration**: Working localhost:6379 connection
- ✅ **CocoIndex Flow**: Proper flow structure with observability

### **Current Mock Implementation**
```python
def extract_entities_with_llm(text: str) -> List[Entity]:
    """Extract entities from text using LLM (mock for now)."""
    # Mock implementation - replace with real LLM call
    entities = []
    
    # Simple keyword-based extraction for demo
    keywords = {
        'bookstack': ('TECHNOLOGY', 'Knowledge management platform'),
        'falkordb': ('TECHNOLOGY', 'Graph database system'),
        # ... more keywords
    }
```

**🎯 Goal**: Replace this with Ollama-powered real entity extraction.

---

## 🚀 **Ollama Integration Strategy**

### **Phase 1: Ollama Setup and Testing**

#### **1.1 Ollama Installation and Model Setup**
```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull recommended models for entity extraction
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull codellama:7b

# Test Ollama is running
curl http://localhost:11434/api/tags
```

#### **1.2 Python Ollama Client Setup**
```python
# Install ollama python client
pip install ollama

# Test connection
import ollama
response = ollama.chat(model='llama3.1:8b', messages=[
    {'role': 'user', 'content': 'Hello, test message'}
])
print(response['message']['content'])
```

### **Phase 2: Entity Extraction Prompt Engineering**

#### **2.1 Entity Extraction Prompt Template**
```python
ENTITY_EXTRACTION_PROMPT = """
You are an expert knowledge graph entity extractor. Extract entities from the following text and classify them into these types:

ENTITY TYPES:
- TECHNOLOGY: Software, frameworks, tools, programming languages, databases
- CONCEPT: Abstract ideas, methodologies, processes, principles
- PERSON: Individual people, authors, developers
- ORGANIZATION: Companies, institutions, teams, groups
- LOCATION: Places, regions, countries, cities
- PRODUCT: Specific products, services, applications

TEXT TO ANALYZE:
{text}

INSTRUCTIONS:
1. Extract ALL significant entities mentioned in the text
2. For each entity, provide:
   - name: The exact entity name (normalized, lowercase)
   - type: One of the types above
   - description: Brief description of what this entity is
3. Focus on technical and domain-specific entities
4. Avoid generic words like "system", "data", "information" unless they're part of a specific term

OUTPUT FORMAT (JSON):
[
  {
    "name": "entity_name",
    "type": "ENTITY_TYPE", 
    "description": "Brief description"
  }
]

Return ONLY the JSON array, no other text.
"""
```

#### **2.2 Relationship Extraction Prompt Template**
```python
RELATIONSHIP_EXTRACTION_PROMPT = """
You are an expert at identifying semantic relationships between entities. Given a list of entities and the original text, identify meaningful relationships.

ENTITIES:
{entities}

ORIGINAL TEXT:
{text}

RELATIONSHIP TYPES:
- relates_to: General relationship
- part_of: Component relationship
- depends_on: Dependency relationship
- implements: Implementation relationship
- uses: Usage relationship
- created_by: Creation relationship

INSTRUCTIONS:
1. Identify relationships between the provided entities
2. Only create relationships that are clearly supported by the text
3. Provide supporting evidence from the text

OUTPUT FORMAT (JSON):
[
  {
    "subject": "entity1_name",
    "predicate": "relationship_type",
    "object": "entity2_name",
    "fact": "Supporting evidence from the text"
  }
]

Return ONLY the JSON array, no other text.
"""
```

### **Phase 3: Implementation Integration**

#### **3.1 Ollama Entity Extractor Class**
```python
import ollama
import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class Entity:
    name: str
    type: str
    description: str

@dataclass  
class Relationship:
    subject: str
    predicate: str
    object: str
    fact: str

class OllamaEntityExtractor:
    def __init__(self, model: str = "llama3.1:8b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.client = ollama.Client(host=base_url)
        
    def extract_entities(self, text: str) -> List[Entity]:
        """Extract entities using Ollama."""
        try:
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=text[:2000])  # Limit text length
            
            response = self.client.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.1}  # Low temperature for consistency
            )
            
            content = response['message']['content'].strip()
            
            # Parse JSON response
            if content.startswith('```json'):
                content = content.replace('```json', '').replace('```', '').strip()
            
            entities_data = json.loads(content)
            
            entities = []
            for entity_data in entities_data:
                entities.append(Entity(
                    name=entity_data['name'].lower().strip(),
                    type=entity_data['type'],
                    description=entity_data['description']
                ))
            
            return entities
            
        except Exception as e:
            logging.error(f"Error extracting entities with Ollama: {e}")
            return []
    
    def extract_relationships(self, text: str, entities: List[Entity]) -> List[Relationship]:
        """Extract relationships using Ollama."""
        try:
            entity_names = [e.name for e in entities]
            entities_str = ", ".join(entity_names)
            
            prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
                entities=entities_str,
                text=text[:2000]
            )
            
            response = self.client.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.1}
            )
            
            content = response['message']['content'].strip()
            
            # Parse JSON response
            if content.startswith('```json'):
                content = content.replace('```json', '').replace('```', '').strip()
            
            relationships_data = json.loads(content)
            
            relationships = []
            for rel_data in relationships_data:
                relationships.append(Relationship(
                    subject=rel_data['subject'].lower().strip(),
                    predicate=rel_data['predicate'],
                    object=rel_data['object'].lower().strip(),
                    fact=rel_data['fact']
                ))
            
            return relationships
            
        except Exception as e:
            logging.error(f"Error extracting relationships with Ollama: {e}")
            return []
```

#### **3.2 Integration into Current Pipeline**

**File**: `flows/bookstack_enhanced_localhost.py`

**Replace the mock functions**:
```python
# Add at top of file
from ollama_entity_extractor import OllamaEntityExtractor

# Initialize global extractor
_OLLAMA_EXTRACTOR = OllamaEntityExtractor(
    model=os.environ.get('OLLAMA_MODEL', 'llama3.1:8b'),
    base_url=os.environ.get('OLLAMA_URL', 'http://localhost:11434')
)

def extract_entities_with_llm(text: str) -> List[Entity]:
    """Extract entities from text using Ollama LLM."""
    return _OLLAMA_EXTRACTOR.extract_entities(text)

def extract_relationships_with_llm(text: str, entities: List[Entity]) -> List[Relationship]:
    """Extract relationships between entities using Ollama LLM."""
    return _OLLAMA_EXTRACTOR.extract_relationships(text, entities)
```

### **Phase 4: Configuration and Environment**

#### **4.1 Environment Variables**
```bash
# Add to .env or environment
OLLAMA_MODEL=llama3.1:8b
OLLAMA_URL=http://localhost:11434
OLLAMA_TIMEOUT=30
OLLAMA_MAX_TEXT_LENGTH=2000
```

#### **4.2 Enhanced run_cocoindex.py**
```python
# Add Ollama environment setup
os.environ.setdefault("OLLAMA_MODEL", "llama3.1:8b")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_TIMEOUT", "30")
```

### **Phase 5: Testing and Validation**

#### **5.1 Ollama Test Script**
Create `test_ollama_extraction.py`:
```python
#!/usr/bin/env python3
"""Test Ollama entity extraction integration."""

from ollama_entity_extractor import OllamaEntityExtractor

def test_ollama_extraction():
    extractor = OllamaEntityExtractor()
    
    test_text = """
    BookStack is a knowledge management platform that integrates with FalkorDB 
    graph database. The API allows developers to export documentation and create 
    comprehensive knowledge graphs using CocoIndex data processing framework.
    """
    
    print("🧪 Testing Ollama Entity Extraction")
    print("=" * 50)
    
    # Test entity extraction
    entities = extractor.extract_entities(test_text)
    print(f"📊 Extracted {len(entities)} entities:")
    for entity in entities:
        print(f"  • {entity.name} ({entity.type}): {entity.description}")
    
    # Test relationship extraction
    relationships = extractor.extract_relationships(test_text, entities)
    print(f"\n🔗 Extracted {len(relationships)} relationships:")
    for rel in relationships:
        print(f"  → {rel.subject} --{rel.predicate}--> {rel.object}")
        print(f"    Fact: {rel.fact}")

if __name__ == "__main__":
    test_ollama_extraction()
```

#### **5.2 Integration Test**
```python
# Test with actual BookStack data
def test_enhanced_pipeline_with_ollama():
    """Test the enhanced pipeline with Ollama integration."""
    # Load a sample BookStack page
    # Run through enhanced extraction
    # Verify results in FalkorDB
    pass
```

---

## 📋 **Implementation Checklist**

### **Prerequisites**
- [ ] Ollama installed and running on localhost:11434
- [ ] Recommended model downloaded (llama3.1:8b)
- [ ] Python ollama client installed (`pip install ollama`)
- [ ] FalkorDB running on localhost:6379
- [ ] PostgreSQL running for CocoIndex observability

### **Implementation Steps**
- [ ] Create `ollama_entity_extractor.py` with OllamaEntityExtractor class
- [ ] Update `flows/bookstack_enhanced_localhost.py` to use Ollama
- [ ] Add environment variables for Ollama configuration
- [ ] Create test script for Ollama extraction
- [ ] Test individual entity extraction
- [ ] Test relationship extraction
- [ ] Run full pipeline test with small dataset
- [ ] Validate results in FalkorDB
- [ ] Run full pipeline with complete BookStack export
- [ ] Performance testing and optimization

### **Validation Criteria**
- [ ] Ollama successfully extracts entities from sample text
- [ ] Entity types are correctly classified
- [ ] Relationships are meaningful and supported by text
- [ ] Integration works with existing CocoIndex flow
- [ ] FalkorDB receives enhanced entities and relationships
- [ ] Performance is acceptable for 153 documents
- [ ] Error handling works for Ollama failures

---

## 🚀 **Expected Improvements**

### **Before (Mock)**
- 17 entities (mostly keyword-based)
- 13 relationships (simple co-occurrence)
- Limited entity types

### **After (Ollama)**
- 50-100+ entities (comprehensive extraction)
- 30-50+ relationships (semantic analysis)
- Full entity type coverage (PERSON, ORGANIZATION, etc.)
- Rich, contextual descriptions
- Accurate relationship classification

---

## 📊 **Performance Considerations**

### **Optimization Strategies**
1. **Text Chunking**: Limit input text to 2000 characters
2. **Batch Processing**: Process multiple documents efficiently
3. **Caching**: Cache results for repeated content
4. **Model Selection**: Use appropriate model size for performance
5. **Timeout Handling**: Graceful fallback for slow responses

### **Monitoring**
- Track extraction time per document
- Monitor Ollama response times
- Log extraction success/failure rates
- Measure entity/relationship quality

---

## 🔧 **Quick Start Commands**

### **1. Setup Ollama**
```bash
# Install and start Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.1:8b
ollama serve
```

### **2. Install Dependencies**
```bash
pip install ollama
```

### **3. Create Ollama Extractor**
```bash
# Copy the OllamaEntityExtractor class to:
# ollama_entity_extractor.py
```

### **4. Update Pipeline**
```bash
# Modify flows/bookstack_enhanced_localhost.py
# Replace mock functions with Ollama integration
```

### **5. Test Integration**
```bash
python test_ollama_extraction.py
```

### **6. Run Enhanced Pipeline**
```bash
python run_cocoindex.py update --setup flows/bookstack_enhanced_localhost.py
```

---

## 📁 **File Structure After Integration**

```
📁 Production Files:
  flows/bookstack_enhanced_localhost.py (✅ Updated with Ollama)
  ollama_entity_extractor.py (🆕 New Ollama integration)
  test_ollama_extraction.py (🆕 New test script)
  export_all_bookstack.py
  run_cocoindex.py (✅ Updated with Ollama env vars)
  test_enhanced_localhost.py
  verify_enhanced_results.py

📁 Data:
  bookstack_export_full/ (153 pages)

📁 Infrastructure:
  docker-compose.cocoindex.yml
  init-postgres.sql
```

---

## 🎯 **Success Metrics Target**

| Metric | Current (Mock) | Target (Ollama) | Improvement |
|--------|----------------|-----------------|-------------|
| **Entities** | 17 | 50-100+ | 3-6x increase |
| **Entity Types** | 3 types | 6 types | 2x coverage |
| **Relationships** | 13 | 30-50+ | 2-4x increase |
| **Quality** | Keyword-based | Semantic analysis | Qualitative leap |
| **Descriptions** | Generic | Contextual | Rich detail |

---

**🎯 This master guide provides everything needed to integrate Ollama-powered advanced entity extraction into your production pipeline!**

**🚀 Ready to transform your knowledge graph with real AI-powered entity extraction!**
