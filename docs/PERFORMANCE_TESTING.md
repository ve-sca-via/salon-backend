# Performance Testing Guide

## Overview
This guide provides instructions for testing API performance and memory usage in a local development environment before deployment. These tools help identify performance bottlenecks, memory leaks, and scalability issues early in the development cycle.

## When to Use These Tools

Performance testing should be conducted in the following scenarios:

- Before deploying new features or significant code changes
- When investigating performance degradation or slow response times
- Prior to anticipated high-traffic events
- During scheduled optimization and performance improvement cycles
- After database schema changes or query modifications

## Setup: Testing Virtual Environment

### Rationale
Performance testing tools require specific dependencies that may conflict with production requirements. A dedicated testing virtual environment isolates these tools from production dependencies and prevents version conflicts.

### Initial Setup

Navigate to the backend project directory and create a dedicated testing virtual environment:

**Windows:**
```bash
cd <backend-directory>
python -m venv venv-testing
.\venv-testing\Scripts\activate
pip install -r requirements-test.txt
```

**macOS/Linux:**
```bash
cd <backend-directory>
python -m venv venv-testing
source venv-testing/bin/activate
pip install -r requirements-test.txt
```

### Activating the Testing Environment

**Windows:**
```bash
.\venv-testing\Scripts\activate
```

**macOS/Linux:**
```bash
source venv-testing/bin/activate
```

### Deactivating and Switching Environments

To return to the production environment:
```bash
deactivate
```

Then activate your production virtual environment as needed.
Prerequisites
Ensure the testing virtual environment is activated before running memory profiling tools.

### Execution Methods

#### Application-Wide Profiling
```bash
python -m memory_profiler main.py
```

#### Function-Specific Profiling
```bash
python -m memory_profiler scripts/profile_memory.py
```

### Interpreting Results
#### Option B: Profile specific functions
```bash
python -m memory_profiler scripts/profile_memory.py
```

### Reading the Output
```
Line #    Mem usage    Increment   Line Contents
================================================
     3     20.5 MiB     20.5 MiB   @profile
     4                             def my_function():
     5     30.2 MiB      9.7 MiB       large_list = [1] * 1000000  # ⚠️ Uses 9.7 MB!
     6     30.2 MiB      0.0 MiB       return len(large_list)
```

     6     30.2 MiB      0.0 MiB       return len(large_list)
```

**Key Metrics:**
- **Mem usage**: Total memory consumed at each line
- **Increment**: Additional memory allocated by that specific line
- **High increment values**: Indicate memory-intensive operations requiring optimization
- **Memory not released**: Potential memory leaks that require investigation

## Load Testing with Locust

### Execution Steps

#### Step 1: Start Local Development Server
Open a terminal and start the application:
```bash
python main.py
```

#### Step 2: Execute Load Test
In a separate terminal, run the load test with the testing virtual environment activated:
```bash
locust -f locustfile.py --users 50 --spawn-rate 5 --host http://localhost:8000
```

#### Step 3: Access Web Interface
Navigate to http://localhost:8089 in your web browser to monitor real-time results.

### Configuration Parameters

- `--users`: Number of concurrent users to simulate
- `--spawn-rate`: Rate at which new users are added per second
- `--host`: Target API URL (use localhost for local testing)
- `--run-time`: Optional duration for the test (e.g., `--run-time 5m`)

### Performance Metrics and Thresholds

**Response Time:**
- Optimal: < 200ms
- Acceptable: 200-500ms
- Requires optimization: > 500ms

**Component | Environment | Purpose |
|-----------|-------------|---------|
| Testing tools | Local development | Pre-deployment testing and analysis |
| requirements-test.txt | Version control | Shared testing dependencies for team |
| requirements.txt | Production | Production dependencies only |
| CI/CD pipeline | Optional | Automated performance regression testing |

**Note:** Performance testing tools should not be deployed to production environments to avoid unnecessary resource consumption and potential security concerns.

## Recommended Testing
| Tool | Location | Why |
1. **Development**: Implement new features in the production virtual environment
2. **Memory Analysis**: Activate testing environment and run memory profiler
3. **Local Server**: Start application server in production environment (Terminal 1)
4. **Load Testing**: Execute Locust tests in testing environment (Terminal 2)
5. **Analysis**: Review metrics in web interface (http://localhost:8089)
6. **Optimization**: Address identified performance issues
7. **Validation**: Re-run tests to confirm improvements
8. **Deployment**: Deploy to production environment after successful validation

### Example Commands

**Terminal 1 (Application Server):**
```bash
# Activate production environment
source venv/bin/activate  # macOS/Linux
# or
.\venv\Scripts\activate   # Windows

# Start application
python main.py
```

**Terminal 2 (Load Testing):**
```bash
# Activate testing environment
source venv-testing/bin/activate  # macOS/Linux
# or
.\venv-testing\Scripts\activate   # Windows

# Run load test
locust -f locustfile.py --users 100 --spawn-rate 10 --host http://localhost:8000

# Deactivate when complete
deactivate
```

## Customizing Load Tests

### Adding Custom Endpoints

Modify `locustfile.py` to include application-specific endpoints

# 9. Deploy to Render (tools NOT deployed)
git push
```

---
from locust import task, HttpUser

class APIUser(HttpUser):
    @task(2)  # Task weight (higher = more frequent execution)
    def test_custom_endpoint(self):
        """Load test for custom endpoint"""
        self.client.get("/api/your-endpoint")
    
    @task(1)
    def test_authenticated_endpoint(self):
        """Load test with authentication"""
        headers = {"Authorization": "Bearer <token>"}
        self.client.get("/api/protected-endpoint", headers=headers)
```

### Adding Memory Profiling to Functions

Decorate functions with the `@profile` decorator:

```python
from memory_profiler import profile

@profile
def process_large_dataset():
    """
    Function with memory profiling enabled
    """
    # Function implementation
    pass
```

## Troubleshooting

### Dependency Conflicts
**Issue:** Package version conflicts between production and testing environments.

**Solution:** Use separate virtual environments as described in the Setup section. Never mix production and testing dependencies in the same environment.

### Test Failures During Load Testing
**Issue:** High failure rates during load testing.

**Common Causes:**
- Database connection pool exhaustion
- Missing or invalid authentication credentials
- Inefficient database queries causing timeouts
- Insufficient system resources (memory, CPU)
- Race conditions in concurrent operations

**Resolution:** Investigate error logs, optimize queries, increase connection pool size, or add proper error handling.

### Memory Profiling Performance Impact
**Issue:** Memory profiling significantly slows down application execution.

**Expected Behavior:** Memory profiling adds overhead. Use it for analysis only, not in production environments.

### Platform-Specific Path Issues
**Issue:** Virtual environment activation commands differ across operating systems.

**Solution:** Refer to the platform-specific commands provided in the Setup section.

## Additional Resources

- [Memory Profiler Documentation](https://pypi.org/project/memory-profiler/)
- [Locust Documentation](https://docs.locust.io/)
- [FastAPI Performance Best Practices](https://fastapi.tiangolo.com/deployment/)
- [Python Virtual Environments Guide](https://docs.python.org/3/library/venv.html)

## 📚 Learn More

- Memory Profiler: https://pypi.org/project/memory-profiler/
- Locust Docs: https://docs.locust.io/
- FastAPI Performance: https://fastapi.tiangolo.com/deployment/
