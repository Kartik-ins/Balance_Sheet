# 🏦 Autonomous Financial Statement Assurance Platform

An AI-powered multi-agent system for automated trial balance validation, variance analysis, and financial statement assurance. Built with autonomous agents that learn from human feedback.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.29+-red.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 🎯 Overview

This platform automates the traditionally manual process of financial statement assurance using a coordinated system of AI agents:

- **Ingestion Agent**: Parses and normalizes trial balance data from various formats
- **Validation Agent**: Runs 12+ validation rules (balance checks, sign conventions, completeness)
- **Variance Agent**: Analyzes period-over-period changes with statistical outlier detection
- **Decision Agent**: Makes auto-approve/escalate decisions based on risk scoring
- **Learning Agent**: Captures human feedback to continuously improve decision thresholds

## ✨ Features

### Core Capabilities
- 📊 **Multi-format ingestion** - CSV, Excel, JSON trial balance files
- ✅ **12+ validation checks** - Debit/credit balance, sign conventions, completeness, duplicates
- 📈 **Statistical variance analysis** - Z-score outlier detection, trend analysis
- 🎯 **Risk-based decisions** - Automated approval for low-risk items, escalation for anomalies
- 🧠 **Continuous learning** - Threshold adjustments based on human override patterns
- 📝 **Complete audit trail** - Every action logged with timestamps and agent attribution

### User Interface
- 📊 **Overview Dashboard** - Pipeline status, key metrics, risk distribution
- ✅ **Validations Tab** - Detailed validation results with severity indicators
- 📈 **Variance Tab** - Interactive charts showing period-over-period changes
- 🎯 **Decisions Tab** - Review queue with approve/reject workflow
- 📝 **Audit Log** - Searchable event history from session and database
- 🧠 **Learning Tab** - Feedback metrics, override rates, improvement suggestions
- 🗄️ **History Tab** - Database browser for historical periods and decisions

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI (8 Tabs)                    │
├─────────────────────────────────────────────────────────────┤
│                   Agent Orchestrator                         │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│ Ingestion│Validation│ Variance │ Decision │    Learning     │
│  Agent   │  Agent   │  Agent   │  Agent   │     Agent       │
├──────────┴──────────┴──────────┴──────────┴─────────────────┤
│                    SQLite Database                           │
│  (Entities, Periods, Balances, Decisions, Feedback, Logs)   │
├─────────────────────────────────────────────────────────────┤
│                  OpenRouter API (Gemma 3 27B)               │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- OpenRouter API key (for LLM-powered explanations)

### Installation

```bash
# Clone the repository
git clone https://github.com/Kartik-ins/Balance_Sheet.git
cd Balance_Sheet

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

### Running the Application

```bash
# Initialize database with sample data
python -m scripts.init_db --seed

# Start the Streamlit UI
streamlit run ui/app.py --server.port 8502
```

Then open http://localhost:8502 in your browser.

## 📁 Project Structure

```
Balance_Sheet/
├── app/
│   ├── agents/           # AI agent implementations
│   │   ├── base.py       # Base agent class
│   │   ├── ingestion.py  # Data ingestion agent
│   │   ├── validation.py # Validation rules agent
│   │   ├── variance.py   # Variance analysis agent
│   │   ├── decision.py   # Decision making agent
│   │   ├── learning.py   # Learning from feedback agent
│   │   └── orchestrator.py # Agent coordination
│   ├── models/           # Pydantic & SQLAlchemy models
│   │   ├── domain.py     # Domain models (Entity, Period, Balance)
│   │   └── database.py   # Database ORM models
│   ├── services/         # Business logic services
│   │   ├── db.py         # Database connection & sessions
│   │   ├── audit.py      # Audit logging service
│   │   └── explanation.py # LLM explanation service
│   └── config.py         # Application configuration
├── ui/
│   └── app.py            # Streamlit application (1400+ lines)
├── scripts/
│   └── init_db.py        # Database initialization & seeding
├── data/
│   ├── assurance.db      # SQLite database
│   └── sample/           # Sample trial balance files
├── tests/                # Test suite
├── requirements.txt      # Python dependencies
├── pyproject.toml        # Project metadata
└── .env.example          # Environment template
```

## ⚙️ Configuration

Create a `.env` file with:

```env
# Required
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Optional
DATABASE_URL=sqlite:///data/assurance.db
LOG_LEVEL=INFO
OPENROUTER_MODEL=google/gemma-3-27b-it:free
```

## 🔄 Workflow

1. **Upload Trial Balance** - CSV/Excel file with account codes, debits, credits
2. **Automatic Processing** - Agents run validation, variance analysis, and risk scoring
3. **Review Decisions** - High-risk items flagged for human review
4. **Provide Feedback** - Approve/reject with reasons to train the system
5. **Continuous Learning** - System adjusts thresholds based on override patterns

## 📊 Validation Rules

| Rule | Description |
|------|-------------|
| Balance Check | Total debits must equal total credits |
| Sign Convention | Assets positive, liabilities negative |
| Completeness | All required accounts present |
| Duplicate Detection | No duplicate account codes |
| Format Validation | Account codes match expected patterns |
| Range Checks | Values within expected bounds |
| Period Consistency | Balances consistent with prior periods |
| Materiality | Large variances flagged for review |

## 🧠 Learning System

The Learning Agent tracks:
- **Override Rate**: How often humans override AI decisions
- **Agreement Rate**: How often humans agree with AI
- **Account Patterns**: Which accounts frequently need review
- **Threshold Suggestions**: Recommended adjustments based on feedback

## 🛠️ Development

```bash
# Run tests
pytest tests/ -v

# Run with hot reload
streamlit run ui/app.py --server.runOnSave true

# Reset database
python -m scripts.init_db --reset --seed
```

## 📝 API Reference

The platform includes a FastAPI backend (optional):

```bash
uvicorn app.main:app --reload --port 8000
```

Endpoints:
- `POST /api/v1/pipeline/run` - Run assurance pipeline
- `GET /api/v1/entities` - List entities
- `GET /api/v1/periods/{entity_id}` - Get periods for entity
- `POST /api/v1/feedback` - Submit decision feedback

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Streamlit](https://streamlit.io/) for the interactive UI
- LLM explanations powered by [OpenRouter](https://openrouter.ai/)
- Statistical analysis with [SciPy](https://scipy.org/) and [Statsmodels](https://www.statsmodels.org/)

---

**Made with ❤️ for financial auditors who deserve better tools**