
transcript = [
    {"role": "customer", "content": "Hi, good afternoon. I'd like to know if I can change the delivery address for my order."},
    {"role": "bot", "content": "Good afternoon! I can help with that. Could you please provide me with your order number?"},
    {"role": "customer", "content": "Yes, it's 73820."},
    {"role": "bot", "content": "Thank you. Let me check... I found your order, but I'm unable to change the delivery address through this channel."},
    {"role": "customer", "content": "So how can I make that change then?"},
    {"role": "bot", "content": "I'm sorry, but I don't have that information available. I'd recommend contacting customer support by phone."},
    {"role": "customer", "content": "Do you have the customer support number?"},
    {"role": "bot", "content": "Unfortunately, I'm unable to provide that number at the moment. I apologize for the inconvenience."},
    {"role": "customer", "content": "Okay, thanks anyway."},
    {"role": "bot", "content": "I'm sorry I couldn't help more. Have a good day."},
]

Command: python tests\llm_manual_test.py

handoff_needed=True reason='order_address_modification_unresolved' summary='Customer requested a delivery address change for order #73820. The bot identified the order but was unable to process the change, guide the customer, or provide the support phone number.' urgency=<Urgency.MEDIUM: 'medium'> suggested_team=<Team.ESCALATIONS: 'escalations'> confidence=0.95 flags=['bot_dead_end', 'unresolved_request', 'time_sensitive_shipping']
