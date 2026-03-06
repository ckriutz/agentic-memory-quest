# Memory Test Prompts

10 rich prompts to test memory storage and retrieval. Each prompt packs multiple facts
the agent should remember. Follow with the recall prompts to verify retention.

## Store (send these 1–10 in order)

### 1 — Arrival & Identity
Hi! My name is Derek, I'm 38 years old, and I just checked into room 412 with my partner Jamie. We're here from Seattle celebrating our 10th anniversary. We drove down in our Tesla and we'll be staying through Sunday with a late checkout. Can you suggest a welcome drink?

### 2 — Dietary Restrictions & Dining
For dinner planning this weekend — I'm allergic to shellfish and Jamie is lactose intolerant. We both love Mediterranean and Japanese cuisine. Last time we visited we had an amazing omakase at the resort restaurant and I'd love to do that again. Oh, and I take my coffee black, no sugar. Any breakfast recommendations?

### 3 — Spa Preferences
I'd like to book some spa treatments. I prefer deep-tissue massages — no Swedish please. I'm also allergic to lavender so make sure none of the oils or products contain it. Jamie absolutely loves hot stone treatments and aromatherapy with eucalyptus. We'd like couples treatments on Saturday afternoon if available. What do you recommend?

### 4 — Fitness & Wellness
I'm currently training for the Boston Marathon in April so I need to keep up my running schedule. I usually run 8 miles before 7 AM. I also do yoga in the evenings — I loved the ocean-view yoga session you offered last time I was here. Jamie prefers Pilates or swimming. Do you have a gym with treadmills and a pool?

### 5 — Activities & Interests
We're big fans of water sports — Jamie is an advanced surfer and I'm an intermediate kayaker. We also enjoy hiking and we've done the coastal bluff trail here before. For something different this trip we'd love to try a sunset sailing excursion or a guided snorkeling tour. Is there anything like that available Saturday?

### 6 — Work & Schedule
I work in software engineering and Jamie is a veterinarian. I might need to hop on a video call Saturday morning around 9 AM, so I'll need good Wi-Fi and a quiet spot. Other than that one call, we're completely unplugged this weekend. I'm normally an early riser but Jamie likes to sleep in until 9. Can you suggest a morning plan that works for both of us?

### 7 — Past Visits & Loyalty
This is actually our third visit to the resort. The first time was in 2022 for a friend's wedding, and the second was last summer when I did the triathlon training camp. I'm a Gold tier loyalty member — member number LM-88421. Last visit the front desk upgraded us to an ocean-view suite and that was incredible. Is there any loyalty perk available this time?

### 8 — Special Requests & Comfort
A few room requests: we prefer extra firm pillows, Jamie needs a hypoallergenic duvet, and we'd love a mini-fridge stocked with sparkling water and oat milk. I also have a slight sensitivity to bright overhead lighting so if the room has dimmable lights that would be perfect. And could we get fresh flowers — anything except lavender of course. What do you have available?

### 9 — Evening Plans & Entertainment
For Saturday night we want something special for our anniversary. We love live jazz, cocktail bars with craft menus, and outdoor seating. Budget isn't a huge concern — we're thinking a tasting-menu dinner followed by drinks somewhere atmospheric. We also enjoy stargazing if there are any dark-sky spots nearby. Can you put together an evening itinerary?

### 10 — Departure & Follow-Up
On Sunday we'll need late checkout — ideally 2 PM if possible since our drive back to Seattle is about 4 hours. Before we leave we'd like to grab brunch somewhere with a good eggs benedict — mine without hollandaise since I prefer it with avocado instead. Also, can you send a summary of everything we booked to my email derek@example.com? And please save all my preferences for next time.

---

## Recall (send these after all 10 store prompts)

| #  | Prompt | Expected Memory Hits |
|----|--------|----------------------|
| R1 | What do you know about me and my partner? | Derek 38yo, Jamie, Seattle, anniversary, room 412 |
| R2 | We want to book dinner — what should you keep in mind? | Shellfish allergy, lactose intolerant, Mediterranean/Japanese, omakase, black coffee |
| R3 | Recommend spa treatments for both of us. | Deep-tissue (no Swedish, no lavender) for Derek; hot stone + eucalyptus for Jamie; couples Saturday PM |
| R4 | Help me plan tomorrow morning's workout. | Marathon training, 8mi before 7AM, yoga evenings, ocean-view yoga; Jamie: Pilates/swimming |
| R5 | What outdoor activities would we enjoy? | Kayak (intermediate), surf (Jamie advanced), coastal bluff trail, sunset sailing, snorkeling |
| R6 | I need a quiet spot Saturday morning — remember why? | Video call at 9AM, software engineer, needs Wi-Fi; Jamie sleeps in until 9 |
| R7 | Have we been here before? | 3rd visit: 2022 wedding, last summer triathlon camp, Gold tier LM-88421, got ocean-view upgrade |
| R8 | Remind me what room preferences we set up. | Extra firm pillows, hypoallergenic duvet, sparkling water + oat milk, dimmable lights, flowers (no lavender) |
| R9 | Plan our anniversary evening. | Live jazz, craft cocktails, outdoor seating, tasting menu, stargazing, budget flexible |
| R10 | What do we need for checkout day? | Late checkout 2PM, 4hr drive to Seattle, brunch eggs benedict (avocado not hollandaise), email derek@example.com, save preferences |
