# CocoIndex Ollama Pipeline Issues & Fixes

## 🔍 Issues Identified

### 1. **Missing Address Parameter in LlmSpec**
**Problem**: Your Ollama LlmSpec configurations were missing the `address` parameter, which is required for external Ollama instances.

**Before**:
```python
llm_spec=cocoindex.LlmSpec(
    api_type=cocoindex.LlmApiType.OLLAMA,
    model="gemma3:12b"
    # Missing address parameter!
)
```

**After**:
```python
llm_spec=cocoindex.LlmSpec(
    api_type=cocoindex.LlmApiType.OLLAMA,
    model="gemma3:12b",
    address="http://100.81.139.20:11434"  # Required for external Ollama
)
```

### 2. **Wrong Target Types for FalkorDB**
**Problem**: Using Neo4j targets for FalkorDB, which uses Redis protocol.

**Before**:
```python
cocoindex.targets.Neo4j(
    connection=falkor_conn_spec,
    mapping=cocoindex.targets.Nodes(label="Episodic")
)
```

**After**:
```python
# Use PostgreSQL for CocoIndex data, custom functions for FalkorDB
cocoindex.targets.Postgres()
```

### 3. **Inconsistent Flow Patterns**
**Problem**: Multiple flow files with different approaches, some bypassing CocoIndex conventions.

**Issues**:
- Custom Ollama clients instead of `ExtractByLlm`
- Inconsistent data structure definitions
- Complex custom functions that don't follow CocoIndex patterns

### 4. **Pipeline Hanging After Setup**
**Problem**: Pipeline stops after setup phase and never processes data.

**Root Causes**:
- Configuration errors in LlmSpec
- Wrong target configurations
- Missing environment variables

## ✅ Solutions Implemented

### 1. **Corrected Flow** (`flows/bookstack_ollama_corrected.py`)
- ✅ Proper `address` parameter in LlmSpec
- ✅ Uses `cocoindex.functions.ExtractByLlm` (official pattern)
- ✅ Consistent dataclass definitions
- ✅ Exports to PostgreSQL (CocoIndex standard)
- ✅ Proper error handling

### 2. **Custom FalkorDB Export** (`flows/falkordb_export.py`)
- ✅ Uses Redis protocol for FalkorDB
- ✅ Implements Graphiti schema compliance
- ✅ Deterministic UUID generation
- ✅ Proper Cypher query construction

### 3. **Comprehensive Test Suite** (`test_ollama_pipeline.py`)
- ✅ Tests Ollama connectivity and model availability
- ✅ Validates FalkorDB connection
- ✅ Checks BookStack data format
- ✅ Verifies CocoIndex installation
- ✅ Tests dataclass definitions and flow syntax

## 🚀 CocoIndex Best Practices Applied

### 1. **LLM Integration Pattern**
```python
# ✅ Correct pattern
doc["analysis"] = doc["text_content"].transform(
    cocoindex.functions.ExtractByLlm(
        llm_spec=cocoindex.LlmSpec(
            api_type=cocoindex.LlmApiType.OLLAMA,
            model="gemma3:12b",
            address=os.environ.get("OLLAMA_URL", "http://100.81.139.20:11434")
        ),
        output_type=DocumentAnalysis,
        instruction="Clear, specific instructions..."
    )
)
```

### 2. **Flow Structure Pattern**
```python
# ✅ Correct pattern
@cocoindex.flow_def(name="FlowName")
def flow_function(flow_builder: FlowBuilder, data_scope: DataScope) -> None:
    # Add sources
    data_scope["documents"] = flow_builder.add_source(...)
    
    # Add collectors
    collector = data_scope.add_collector()
    
    # Process data
    with data_scope["documents"].row() as doc:
        doc["field"] = doc["content"].transform(...)
        collector.collect(...)
    
    # Export data
    collector.export("table_name", cocoindex.targets.Postgres(), ...)
```

### 3. **Transform Functions**
```python
# ✅ Correct pattern
@cocoindex.op.function()
def custom_transform(input_data: InputType) -> OutputType:
    # Process data
    return result
```

## 🔧 Environment Variables Required

```bash
# Ollama Configuration
export OLLAMA_URL="http://100.81.139.20:11434"

# FalkorDB Configuration
export FALKOR_HOST="localhost"
export FALKOR_PORT="6379"
export FALKOR_GRAPH="graphiti_migration"

# CocoIndex Database
export COCOINDEX_DATABASE_URL="postgresql://cocoindex:cocoindex@localhost:5433/cocoindex"
```

## 🧪 Testing & Validation

### Run the Test Suite
```bash
python test_ollama_pipeline.py
```

### Expected Output
```
🧪 CocoIndex Ollama Pipeline Test Suite
==================================================
✅ Environment variables configured

🔍 Testing CocoIndex Installation...
✅ CocoIndex imported successfully
✅ CocoIndex core classes available
✅ CocoIndex LLM functions available

🔍 Testing Dataclass Definitions...
✅ Entity dataclass works
✅ Relationship dataclass works
✅ DocumentSummary dataclass works
✅ DocumentAnalysis dataclass works

🔍 Testing Flow Syntax...
✅ Flow function imports successfully
✅ Flow properly decorated with name: BookStackOllamaCorrect

🔍 Testing BookStack Data...
✅ Found 153 BookStack JSON files
✅ Sample JSON file has required fields

🔍 Testing Ollama Connectivity...
✅ Ollama server accessible at http://100.81.139.20:11434
📋 Available models: ['gemma3:12b', ...]
✅ gemma3:12b model is available

🔍 Testing FalkorDB Connectivity...
✅ Connected to FalkorDB at localhost:6379
✅ FalkorDB test successful. Current node count: [...]

📊 TEST SUMMARY
==================================================
✅ PASS CocoIndex Installation
✅ PASS Dataclass Definitions
✅ PASS Flow Syntax
✅ PASS BookStack Data
✅ PASS Ollama Connectivity
✅ PASS FalkorDB Connectivity

🎯 Overall: 6/6 tests passed
🎉 All tests passed! Pipeline should work correctly.
```

## 🚀 Running the Corrected Pipeline

### 1. Setup the Flow
```bash
python run_cocoindex.py update --setup flows/bookstack_ollama_corrected.py
```

### 2. Run the Pipeline
```bash
python run_cocoindex.py update flows/bookstack_ollama_corrected.py
```

### 3. Monitor Progress
The pipeline will:
1. ✅ Load BookStack JSON files
2. ✅ Extract text from HTML content
3. ✅ Call Ollama for entity/relationship extraction
4. ✅ Store results in PostgreSQL
5. ✅ Export to FalkorDB using custom functions

## 🔍 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `Connection refused to Ollama` | Check OLLAMA_URL and ensure Ollama server is running |
| `Model not found: gemma3:12b` | Run `ollama pull gemma3:12b` on the Ollama server |
| `FalkorDB connection failed` | Check FALKOR_HOST/PORT and ensure FalkorDB is running |
| `Pipeline hangs after setup` | Check environment variables and run test suite |

### Debug Commands
```bash
# Test individual components
python test_ollama_pipeline.py

# Test FalkorDB connection
python flows/falkordb_export.py

# Check Ollama models
curl http://100.81.139.20:11434/api/tags
```

## 📈 Expected Results

After successful pipeline execution:
- **PostgreSQL**: Contains extracted entities, relationships, and document metadata
- **FalkorDB**: Contains Graphiti-compliant knowledge graph with:
  - Episodic nodes (documents)
  - Entity nodes (extracted entities)
  - MENTIONS relationships (document → entity)
  - RELATES_TO relationships (entity → entity)

## 🎯 Next Steps

1. **Run the test suite** to validate your environment
2. **Execute the corrected pipeline** with proper CocoIndex conventions
3. **Monitor the results** in both PostgreSQL and FalkorDB
4. **Integrate with Graphiti** for advanced knowledge graph operations
