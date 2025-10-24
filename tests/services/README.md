# Services Unit Tests

This directory contains comprehensive unit tests for all services in the Gardebot application.

## Coverage Summary

All services achieve **100% test coverage**:

- `events.py` (EventService) - 43 statements, 100% coverage
- `group_service.py` (GroupService) - 27 statements, 100% coverage
- `message_service.py` (MessageService) - 51 statements, 100% coverage
- `onduty.py` (OnDutyService) - 70 statements, 100% coverage
- `poll_service.py` (PollService) - 48 statements, 100% coverage
- `sapeur.py` (SapeurService) - 29 statements, 100% coverage
- `votes.py` (VoteService) - 48 statements, 100% coverage

**Total: 316 statements, 0 missed, 100% coverage**

## Test Files

- `test_events.py` - Tests for EventService (13 test methods)
- `test_group_service.py` - Tests for GroupService (5 test methods)
- `test_message_service.py` - Tests for MessageService (14 test methods)
- `test_onduty.py` - Tests for OnDutyService (19 test methods)
- `test_poll_service.py` - Tests for PollService (10 test methods)
- `test_sapeur.py` - Tests for SapeurService (8 test methods)
- `test_votes.py` - Tests for VoteService (17 test methods)

**Total: 80 test methods, all passing**

## Running Tests

To run all service tests:
```bash
python -m unittest discover tests/services -v
```

To run tests with coverage:
```bash
python -m coverage run --source=src/gardebot/services -m unittest discover tests/services
python -m coverage report
```

## Test Characteristics

- **Framework**: Pure Python `unittest` (no pytest dependency)
- **Mocking**: Extensive use of `unittest.mock` for isolation
- **Clean & Short**: Each test is focused and concise
- **Comprehensive**: Tests cover all methods including edge cases, error conditions, and logging
- **Isolated**: Each test uses mocks to avoid dependencies on external services
- **Well-documented**: Each test has clear docstrings explaining its purpose

## Key Testing Patterns

1. **Service Initialization**: Testing both default and custom repository injection
2. **Happy Path**: Testing normal operation flows
3. **Error Handling**: Testing exception scenarios and error logging
4. **Edge Cases**: Testing empty data, missing fields, boundary conditions
5. **Integration Points**: Testing interactions between services through mocking
6. **Logging**: Testing debug, info, and error log statements
7. **Data Transformation**: Testing DataFrame operations and data processing
