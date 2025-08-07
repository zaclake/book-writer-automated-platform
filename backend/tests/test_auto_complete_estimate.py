#!/usr/bin/env python3
"""
Unit tests for auto-complete credit estimation functionality.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

# Add backend directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.auto_complete.estimate_utils import (
    estimate_chapter_credits,
    estimate_auto_complete_credits,
    _get_quality_multiplier,
    _get_retry_multiplier,
    get_estimation_notes
)

class TestQualityMultipliers:
    """Test quality and retry multiplier functions."""
    
    def test_quality_multiplier_ranges(self):
        """Test quality multiplier returns correct values for different thresholds."""
        assert _get_quality_multiplier(9.5) == 2.5  # Extremely high quality
        assert _get_quality_multiplier(8.5) == 2.0  # High quality
        assert _get_quality_multiplier(7.5) == 1.7  # Good quality
        assert _get_quality_multiplier(6.5) == 1.4  # Standard quality
        assert _get_quality_multiplier(5.0) == 1.2  # Basic quality
    
    def test_retry_multiplier_ranges(self):
        """Test retry multiplier returns correct values for different thresholds."""
        assert _get_retry_multiplier(9.5) == 1.8  # May need multiple retries
        assert _get_retry_multiplier(8.5) == 1.5  # Some retries expected
        assert _get_retry_multiplier(7.5) == 1.3  # Occasional retries
        assert _get_retry_multiplier(5.0) == 1.1  # Minimal retries

class TestEstimationNotes:
    """Test estimation notes generation."""
    
    def test_high_quality_notes(self):
        """Test notes for high quality threshold."""
        notes = get_estimation_notes(8.5, 15)
        assert "High quality threshold may require additional retries" in notes
    
    def test_large_book_notes(self):
        """Test notes for large book projects."""
        notes = get_estimation_notes(7.0, 25)
        assert "Large book projects benefit from chapter-by-chapter monitoring" in notes
    
    def test_low_quality_notes(self):
        """Test notes for low quality threshold."""
        notes = get_estimation_notes(5.0, 15)
        assert "Lower quality threshold provides faster, more economical generation" in notes

class TestChapterEstimation:
    """Test single chapter credit estimation."""
    
    @patch('backend.auto_complete.estimate_utils.get_pricing_registry')
    def test_estimate_chapter_credits_success(self, mock_get_registry):
        """Test successful chapter credit estimation."""
        # Mock pricing registry
        mock_registry = Mock()
        mock_registry.is_available.return_value = True
        mock_get_registry.return_value = mock_registry
        
        # Mock credit calculation result
        mock_credit_calc = Mock()
        mock_credit_calc.credits = 150
        mock_credit_calc.raw_cost_usd = 0.75
        mock_credit_calc.markup_applied = 5.0
        mock_credit_calc.calculation_details = {'provider': 'openai', 'model': 'gpt-4o'}
        mock_registry.estimate_credits.return_value = mock_credit_calc
        
        # Test estimation
        result = estimate_chapter_credits(
            words_per_chapter=4000,
            quality_threshold=7.0,
            model='gpt-4o',
            pricing_registry=mock_registry
        )
        
        # Verify results
        assert result['credits'] == 150
        assert result['raw_cost_usd'] == 0.75
        assert result['markup_applied'] == 5.0
        assert 'calculation_details' in result
        assert result['calculation_details']['words_per_chapter'] == 4000
        assert result['calculation_details']['quality_threshold'] == 7.0
        assert result['calculation_details']['model'] == 'gpt-4o'
    
    @patch('backend.auto_complete.estimate_utils.get_pricing_registry')
    def test_estimate_chapter_credits_no_registry(self, mock_get_registry):
        """Test chapter estimation when pricing registry is unavailable."""
        mock_get_registry.return_value = None
        
        result = estimate_chapter_credits(
            words_per_chapter=4000,
            quality_threshold=7.0,
            model='gpt-4o'
        )
        
        assert result['credits'] == 0
        assert result['raw_cost_usd'] == 0.0
        assert 'error' in result
        assert 'Pricing service unavailable' in result['error']
    
    def test_estimate_chapter_credits_exception_handling(self):
        """Test error handling in chapter estimation."""
        # Mock registry that raises an exception
        mock_registry = Mock()
        mock_registry.is_available.return_value = True
        mock_registry.estimate_credits.side_effect = Exception("Test error")
        
        result = estimate_chapter_credits(
            words_per_chapter=4000,
            quality_threshold=7.0,
            model='gpt-4o',
            pricing_registry=mock_registry
        )
        
        assert result['credits'] == 0
        assert result['raw_cost_usd'] == 0.0
        assert 'error' in result
        assert 'Test error' in result['error']

class TestAutoCompleteEstimation:
    """Test full auto-complete book estimation."""
    
    @patch('backend.auto_complete.estimate_utils.estimate_chapter_credits')
    def test_estimate_auto_complete_credits_success(self, mock_chapter_estimate):
        """Test successful auto-complete estimation."""
        # Mock chapter estimation
        mock_chapter_estimate.return_value = {
            'credits': 150,
            'raw_cost_usd': 0.75,
            'markup_applied': 5.0,
            'calculation_details': {'test': 'data'}
        }
        
        # Test estimation
        result = estimate_auto_complete_credits(
            total_chapters=20,
            words_per_chapter=4000,
            quality_threshold=7.0,
            model='gpt-4o'
        )
        
        # Verify results
        assert result['total_chapters'] == 20
        assert result['words_per_chapter'] == 4000
        assert result['total_words'] == 80000
        assert result['quality_threshold'] == 7.0
        assert result['credits_per_chapter'] == 150
        assert result['base_credits'] == 3000  # 150 * 20
        assert result['overhead_credits'] == 150  # 5% of 3000
        assert result['estimated_total_credits'] == 3150  # 3000 + 150
        assert 'calculation_details' in result
    
    @patch('backend.auto_complete.estimate_utils.estimate_chapter_credits')
    def test_estimate_auto_complete_credits_chapter_error(self, mock_chapter_estimate):
        """Test auto-complete estimation when chapter estimation fails."""
        # Mock chapter estimation error
        mock_chapter_estimate.return_value = {
            'error': 'Chapter estimation failed'
        }
        
        result = estimate_auto_complete_credits(
            total_chapters=20,
            words_per_chapter=4000,
            quality_threshold=7.0,
            model='gpt-4o'
        )
        
        assert 'error' in result
        assert 'Chapter estimation failed' in result['error']
    
    def test_estimate_auto_complete_credits_exception_handling(self):
        """Test error handling in auto-complete estimation."""
        # This will fail when trying to import the module
        with patch('backend.auto_complete.estimate_utils.estimate_chapter_credits', side_effect=Exception("Test error")):
            result = estimate_auto_complete_credits(
                total_chapters=20,
                words_per_chapter=4000,
                quality_threshold=7.0,
                model='gpt-4o'
            )
            
            assert 'error' in result
            assert 'Test error' in result['error']
            assert result['estimated_total_credits'] == 0

class TestTokenCalculations:
    """Test token calculation accuracy."""
    
    @patch('backend.auto_complete.estimate_utils.get_pricing_registry')
    def test_token_calculations(self, mock_get_registry):
        """Test that token calculations follow expected patterns."""
        # Mock pricing registry
        mock_registry = Mock()
        mock_registry.is_available.return_value = True
        mock_get_registry.return_value = mock_registry
        
        # Mock credit calculation result
        mock_credit_calc = Mock()
        mock_credit_calc.credits = 100
        mock_credit_calc.raw_cost_usd = 0.50
        mock_credit_calc.markup_applied = 5.0
        mock_credit_calc.calculation_details = {}
        mock_registry.estimate_credits.return_value = mock_credit_calc
        
        # Test estimation
        result = estimate_chapter_credits(
            words_per_chapter=2000,  # Smaller chapter
            quality_threshold=7.0,
            model='gpt-4o',
            pricing_registry=mock_registry
        )
        
        # Verify token calculations in details
        details = result['calculation_details']
        assert details['words_per_chapter'] == 2000
        assert details['base_input_tokens'] == int(2000 * 1.3)  # 2600
        assert details['base_output_tokens'] == int(2000 * 1.3)  # 2600
        assert details['quality_multiplier'] == 1.7  # For threshold 7.0
        assert details['retry_multiplier'] == 1.3   # For threshold 7.0
        
        # Check that pricing registry was called with correct usage data
        mock_registry.estimate_credits.assert_called_once()
        call_args = mock_registry.estimate_credits.call_args
        assert call_args[0][0] == 'openai'
        assert call_args[0][1] == 'gpt-4o'
        usage_data = call_args[0][2]
        assert 'prompt_tokens' in usage_data
        assert 'completion_tokens' in usage_data
        assert 'total_tokens' in usage_data

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
