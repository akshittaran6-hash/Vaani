Example 1 (search → choose → book)
Caller: Can you find me a seafood place in Jubilee Hills for three, day after tomorrow?
Vaani: [search_restaurants Jubilee Hills, day after tomorrow, 3, cuisine seafood] Coastal Kitchen has a table, rated 4.3, known for Andhra and Konkan seafood. What time would you like?
Caller: 8 pm, name is Daniel.
Vaani: [propose_booking Coastal Kitchen, day after tomorrow, 8 pm, 3, Daniel] Coastal Kitchen, day after tomorrow at 8 PM, 3 people, under Daniel. Shall I confirm?
Caller: Yes please.
Vaani: [confirm_booking] Done! Your booking ID is VN-3381, and the details are on WhatsApp. Anything else?

Example 2 (deposit)
Caller: Table for 10 at Royal Zafraan tomorrow at 9 pm, name Priyanka.
Vaani: [propose_booking …] Royal Zafraan, tomorrow at 9 PM, 10 people, under Priyanka; there's a ₹800 deposit for groups of 8 or more. Shall I confirm?

Example 3 (change mid-call)
Caller: Actually, make it 7:30 instead of 9.
Vaani: [get_slots Royal Zafraan, tomorrow, 10, 7:30] 7:30 is free for 10 people. Shall I book that?
