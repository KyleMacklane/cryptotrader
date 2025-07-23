import pytest
from unittest.mock import MagicMock, patch
from main import calculate_and_distribute_profits
from account_manager import AccountManager


@pytest.fixture
def mock_context():
    return MagicMock()

@pytest.fixture
def account_manager(tmp_path):
    csv_file = tmp_path / "test_accounts.csv"
    return AccountManager(csv_file)

def test_profit_distribution(account_manager, mock_context):
    # Setup test accounts
    account_manager.add_user_if_not_exists("tg_user1", "server", "user1")
    account_manager.process_deposit("user1", 1000)  # $1000 deposit → $900 net (balance), $450 allocated to MT5
    
    # Test 10% profit ($45 profit per user)
    with patch('main.MT5Service') as mock_mt5:
        mock_mt5.return_value.get_balance.return_value = 10450  # $450 profit
        result = calculate_and_distribute_profits(mock_context)
        
        assert result is True
        user = account_manager.get_account_info("user1")
        assert float(user["balance"]) > 900  # Should have increased



        