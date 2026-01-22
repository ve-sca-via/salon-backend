"""
Memory profiling script for the Salon Management API

Installation:
    pip install memory-profiler psutil matplotlib

Usage:
    # Profile all operations
    python -m memory_profiler scripts/profile_memory.py
    
    # Profile specific operation
    python -m memory_profiler scripts/profile_memory.py --operation bookings
    
    # With detailed output
    python -m memory_profiler scripts/profile_memory.py --verbose
    
    # Generate memory usage plot
    mprof run scripts/profile_memory.py
    mprof plot
"""
from memory_profiler import profile
import sys
import os
import argparse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Track overall memory stats
memory_stats = {}


def log_memory(operation: str, start_mem: float, end_mem: float):
    """Log memory usage statistics"""
    memory_stats[operation] = {
        'start_mb': start_mem,
        'end_mb': end_mem,
        'delta_mb': end_mem - start_mem
    }


@profile
def test_booking_processing():
    """Profile booking creation and processing with realistic data"""
    print("\n[Bookings] Testing booking processing...")
    
    # Simulate bulk booking data
    bookings = []
    for i in range(1000):
        booking = {
            'id': f'booking_{i}',
            'customer_id': f'customer_{i % 100}',
            'salon_id': f'salon_{i % 50}',
            'service_ids': [f'service_{j}' for j in range(i % 5 + 1)],
            'staff_id': f'staff_{i % 20}',
            'booking_time': datetime.now() + timedelta(hours=i),
            'duration': 60,
            'total_price': 50.0 + (i % 100),
            'status': 'confirmed',
            'notes': f'Test booking {i}' * 10,  # Some text data
        }
        bookings.append(booking)
    
    print(f"  Created {len(bookings)} booking objects")
    
    # Process bookings (simulate operations)
    processed = []
    for booking in bookings:
        processed_booking = {
            **booking,
            'processed_at': datetime.now(),
            'confirmation_sent': True
        }
        processed.append(processed_booking)
    
    print(f"  Processed {len(processed)} bookings")
    
    # Simulate JSON serialization (common in API responses)
    json_data = json.dumps(processed[:100])
    print(f"  Serialized data size: {len(json_data)} bytes")
    
    return processed


@profile
def test_customer_data_operations():
    """Profile customer data loading and filtering"""
    print("\n[Customers] Testing customer data operations...")
    
    # Simulate customer database records
    customers = []
    for i in range(5000):
        customer = {
            'id': f'customer_{i}',
            'email': f'customer{i}@example.com',
            'phone': f'+1234567{i:04d}',
            'first_name': f'FirstName{i}',
            'last_name': f'LastName{i}',
            'preferences': {
                'notification_email': True,
                'notification_sms': i % 2 == 0,
                'favorite_services': [f'service_{j}' for j in range(i % 10)],
                'preferred_staff': [f'staff_{j}' for j in range(i % 5)],
            },
            'booking_history': [f'booking_{j}' for j in range(i % 50)],
            'loyalty_points': i * 10,
            'created_at': datetime.now() - timedelta(days=i),
        }
        customers.append(customer)
    
    print(f"  Created {len(customers)} customer records")
    
    # Filter operations
    active_customers = [c for c in customers if c['loyalty_points'] > 5000]
    print(f"  Filtered to {len(active_customers)} active customers")
    
    # Sort by loyalty points
    sorted_customers = sorted(customers, key=lambda x: x['loyalty_points'], reverse=True)
    top_100 = sorted_customers[:100]
    print(f"  Retrieved top {len(top_100)} customers")
    
    return customers


@profile
def test_salon_location_queries():
    """Profile salon and location data operations"""
    print("\n[Salons] Testing salon location queries...")
    
    # Simulate salon data with location information
    salons = []
    for i in range(500):
        salon = {
            'id': f'salon_{i}',
            'name': f'Salon {i}',
            'latitude': 40.7128 + (i % 100) * 0.01,
            'longitude': -74.0060 + (i % 100) * 0.01,
            'address': f'{i} Main Street, City, State',
            'services': [
                {'id': f'service_{j}', 'name': f'Service {j}', 'price': 50 + j * 10}
                for j in range(20)
            ],
            'staff': [
                {'id': f'staff_{j}', 'name': f'Staff {j}', 'specialties': [f'spec_{k}' for k in range(5)]}
                for j in range(10)
            ],
            'operating_hours': {
                day: {'open': '09:00', 'close': '21:00'}
                for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            },
            'rating': 4.0 + (i % 10) * 0.1,
            'reviews_count': i * 5,
        }
        salons.append(salon)
    
    print(f"  Created {len(salons)} salon records")
    
    # Distance calculation (simulate geospatial queries)
    user_lat, user_lng = 40.7128, -74.0060
    nearby_salons = []
    for salon in salons:
        distance = ((salon['latitude'] - user_lat) ** 2 + 
                   (salon['longitude'] - user_lng) ** 2) ** 0.5
        if distance < 0.5:  # Within ~50km
            nearby_salons.append({**salon, 'distance': distance})
    
    print(f"  Found {len(nearby_salons)} nearby salons")
    
    return salons


@profile
def test_payment_processing():
    """Profile payment data handling"""
    print("\n[Payments] Testing payment processing...")
    
    # Simulate payment transactions
    payments = []
    for i in range(2000):
        payment = {
            'id': f'payment_{i}',
            'booking_id': f'booking_{i}',
            'amount': 50.0 + (i % 500),
            'currency': 'USD',
            'payment_method': ['card', 'cash', 'wallet'][i % 3],
            'status': ['pending', 'completed', 'failed'][i % 10 // 4],
            'transaction_id': f'txn_{i}_{int(time.time())}',
            'metadata': {
                'card_last4': f'{i:04d}',
                'billing_address': f'{i} Payment St, City',
                'receipt_url': f'https://receipts.example.com/{i}',
            },
            'created_at': datetime.now() - timedelta(minutes=i),
        }
        payments.append(payment)
    
    print(f"  Created {len(payments)} payment records")
    
    # Calculate statistics
    total_revenue = sum(p['amount'] for p in payments if p['status'] == 'completed')
    successful_payments = [p for p in payments if p['status'] == 'completed']
    failed_payments = [p for p in payments if p['status'] == 'failed']
    
    print(f"  Total revenue: ${total_revenue:,.2f}")
    print(f"  Successful: {len(successful_payments)}, Failed: {len(failed_payments)}")
    
    return payments


@profile
def test_real_time_data():
    """Profile real-time data structures"""
    print("\n[Real-time] Testing real-time data handling...")
    
    # Simulate real-time events
    events = []
    for i in range(10000):
        event = {
            'event_id': f'event_{i}',
            'event_type': ['booking_created', 'booking_updated', 'payment_completed', 
                          'staff_check_in', 'customer_arrived'][i % 5],
            'timestamp': datetime.now() - timedelta(seconds=i),
            'data': {
                'entity_id': f'entity_{i}',
                'changes': {'field': f'value_{i}'},
            },
        }
        events.append(event)
    
    print(f"  Created {len(events)} real-time events")
    
    # Group events by type
    event_groups = {}
    for event in events:
        event_type = event['event_type']
        if event_type not in event_groups:
            event_groups[event_type] = []
        event_groups[event_type].append(event)
    
    for event_type, group_events in event_groups.items():
        print(f"  {event_type}: {len(group_events)} events")
    
    return events


@profile
def test_data_aggregation():
    """Profile complex data aggregation operations"""
    print("\n[Aggregation] Testing data aggregation...")
    
    # Create nested data structure
    data = {
        'salons': {
            f'salon_{i}': {
                'bookings': [
                    {'id': f'booking_{j}', 'amount': j * 10}
                    for j in range(i % 100)
                ]
            }
            for i in range(200)
        }
    }
    
    print(f"  Created nested data structure")
    
    # Aggregate statistics
    salon_stats = {}
    for salon_id, salon_data in data['salons'].items():
        total_bookings = len(salon_data['bookings'])
        total_revenue = sum(b['amount'] for b in salon_data['bookings'])
        salon_stats[salon_id] = {
            'bookings': total_bookings,
            'revenue': total_revenue,
            'avg_booking_value': total_revenue / total_bookings if total_bookings > 0 else 0
        }
    
    print(f"  Aggregated stats for {len(salon_stats)} salons")
    
    return salon_stats


def print_summary():
    """Print memory usage summary"""
    if not memory_stats:
        return
    
    print("\n" + "=" * 70)
    print("MEMORY USAGE SUMMARY")
    print("=" * 70)
    print(f"{'Operation':<30} {'Start (MB)':<12} {'End (MB)':<12} {'Delta (MB)':<12}")
    print("-" * 70)
    
    for operation, stats in memory_stats.items():
        print(f"{operation:<30} {stats['start_mb']:>10.2f}  {stats['end_mb']:>10.2f}  {stats['delta_mb']:>10.2f}")
    
    print("-" * 70)
    total_delta = sum(s['delta_mb'] for s in memory_stats.values())
    print(f"{'Total Memory Delta':<30} {'':<12} {'':<12} {total_delta:>10.2f}")
    print("=" * 70)


def main():
    """Main profiling function"""
    parser = argparse.ArgumentParser(description='Memory profiling for Salon Management API')
    parser.add_argument(
        '--operation',
        choices=['bookings', 'customers', 'salons', 'payments', 'realtime', 'aggregation', 'all'],
        default='all',
        help='Specific operation to profile'
    )
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("MEMORY PROFILING - SALON MANAGEMENT API")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    operations = {
        'bookings': test_booking_processing,
        'customers': test_customer_data_operations,
        'salons': test_salon_location_queries,
        'payments': test_payment_processing,
        'realtime': test_real_time_data,
        'aggregation': test_data_aggregation,
    }
    
    if args.operation == 'all':
        for name, func in operations.items():
            print(f"\n{'=' * 70}")
            print(f"Running: {name}")
            print('=' * 70)
            func()
    else:
        operations[args.operation]()
    
    print_summary()
    
    print("\n" + "=" * 70)
    print("PROFILING COMPLETE")
    print("=" * 70)
    print("\nTips:")
    print("  - Run 'mprof run scripts/profile_memory.py' for visual plots")
    print("  - Run 'mprof plot' to view the memory usage graph")
    print("  - Use --operation flag to profile specific components")
    print("=" * 70)


if __name__ == "__main__":
    main()
