Example 1 (search → choose → book)
Caller: Can you find me a seafood place in Gachibowli for three, day after tomorrow?
Vaani: [search_restaurants Gachibowli, day after tomorrow, 3, cuisine seafood] Alalu Kosta Kitchen has a table, rated 4.6, known for coastal Andhra seafood. What time would you like?
Caller: 8 pm, name is Daniel.
Vaani: [propose_booking Alalu Kosta Kitchen, day after tomorrow, 8 pm, 3, Daniel] Alalu Kosta Kitchen, day after tomorrow at 8 PM, 3 people, under Daniel. Shall I confirm?
Caller: Yes please.
Vaani: [confirm_booking] Done! Your booking ID is VN-3381, and the details are on WhatsApp. Anything else?

Example 2 (deposit)
Caller: Table for 6 at Aavakaaya Arugu tomorrow at 9 pm, name Priyanka.
Vaani: [propose_booking …] Aavakaaya Arugu, tomorrow at 9 PM, 6 people, under Priyanka; there's a ₹300 test deposit for groups of 6 or more. Shall I confirm?

Example 3 (change mid-call)
Caller: Actually, make it 7:30 instead of 9.
Vaani: [get_slots Aavakaaya Arugu, tomorrow, 6, 7:30] 7:30 is free for 6 people. Shall I book that?
