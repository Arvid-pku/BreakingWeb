"""Batch 02 seed builders — Scheduling and Negotiation tasks.

Registers builders for:
- schedule_recovery
- interview_scheduling
- travel_itinerary_resolution
- multi_party_rsvp
- contract_negotiation_tracker
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from breakingweb.backend.models.gmail import Email
from breakingweb.tasks._seed_builders import SeedContext, _register


# ---------------------------------------------------------------------------
# Gmail: Schedule Recovery
# ---------------------------------------------------------------------------

@_register("schedule_recovery")
def build_schedule_recovery(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Build the schedule recovery scenario: a 3-message thread with a pre-seeded
    user confirmation that is later cancelled, a separate replacement email,
    a decoy suggestion from a colleague, a standup invite showing a conflict,
    and a similar-subject decoy.
    """
    hana_name = "Hana Yilmaz"
    hana_email = ctx.email_for_name(hana_name, domain="scheduling.thornton.com")

    max_name = "Max Orlov"
    max_email = ctx.email_for_name(max_name, domain="scheduling.thornton.com")

    priya_name = "Priya Desai"
    priya_email = ctx.email_for_name(priya_name, domain="scheduling.thornton.com")

    original_thread_id = ctx.next_id("thread")

    # Message 1: Hana proposes Wednesday 10 AM
    proposal_email = ctx.email(
        from_name=hana_name,
        from_addr=hana_email,
        subject="Q2 Planning Sync — Time Proposal",
        body=ctx.format_email_body(
            "Hi,",
            "Let's meet Wednesday at 10:00 AM in Room 4B to kick off Q2 planning.",
            "Let me know if this works for you.",
            signoff_name=ctx.first_name(hana_name),
        ),
        timestamp=ctx.now - timedelta(days=2),
        thread_id=original_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Message 2: Pre-seeded user confirmation (from the user)
    user_confirmation = Email(
        id=ctx.next_id("email"),
        from_name=ctx.owner_name,
        from_addr=ctx.owner_email,
        to=[hana_email],
        cc=[],
        subject="Re: Q2 Planning Sync — Time Proposal",
        body=ctx.format_email_body(
            "Confirmed: Wednesday, 10:00 AM.",
            signoff_name=ctx.first_name(ctx.owner_name),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=22),
        is_read=True,
        labels=["inbox", "sent"],
        thread_id=original_thread_id,
        in_reply_to=proposal_email.id,
        attachments=[],
    )

    # Message 3: Hana cancels Wednesday 10 AM
    cancellation_email = ctx.email(
        from_name=hana_name,
        from_addr=hana_email,
        subject="Q2 Planning Sync — Time Proposal",
        body=ctx.format_email_body(
            "Sorry, Wednesday 10 AM is cancelled due to a room conflict. Will send a new time shortly.",
            signoff_name=ctx.first_name(hana_name),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=18),
        thread_id=original_thread_id,
        labels=["inbox"],
    )

    # Separate email: Hana proposes Thursday 2 PM
    new_time_thread_id = ctx.next_id("thread")
    new_time_email = ctx.email(
        from_name=hana_name,
        from_addr=hana_email,
        subject="Q2 Planning Sync — New Time",
        body=ctx.format_email_body(
            "New proposed time: Thursday at 2:00 PM, Room 6A.",
            "Let me know if this works.",
            signoff_name=ctx.first_name(hana_name),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=12),
        thread_id=new_time_thread_id,
        labels=["inbox"],
    )

    # Decoy: Max suggests Friday 4 PM (conflicts with standup)
    max_thread_id = ctx.next_id("thread")
    max_suggestion_email = ctx.email(
        from_name=max_name,
        from_addr=max_email,
        subject="Re: Q2 planning — alternate time?",
        body=ctx.format_email_body(
            "How about Friday at 4:00 PM? I'm free then and it gives us more prep time.",
            signoff_name=ctx.first_name(max_name),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=6),
        thread_id=max_thread_id,
        labels=["inbox"],
    )

    # Standup invite showing Friday 4 PM conflict
    standup_thread_id = ctx.next_id("thread")
    standup_email = ctx.email(
        from_name="Team Calendar",
        from_addr="calendar@scheduling.thornton.com",
        subject="Weekly Standup — Standing Invite",
        body=ctx.format_email_body(
            "Recurring: Every Friday, 4:00 PM - 4:30 PM. All team members required.",
            "Location: Main Conference Room.",
            "This is a standing invite — do not RSVP.",
        ),
        timestamp=ctx.now - timedelta(days=14),
        thread_id=standup_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Similar-subject decoy from Priya Desai
    decoy_thread_id = ctx.next_id("thread")
    decoy_priya_email = ctx.email(
        from_name=priya_name,
        from_addr=priya_email,
        subject="Q2 Budget Sync — Time Cancelled",
        body=ctx.format_email_body(
            "The Q2 budget sync originally scheduled for Thursday at 2:00 PM has been moved to Monday at 11:00 AM.",
            "Please update your calendars.",
            signoff_name=ctx.first_name(priya_name),
        ),
        timestamp=ctx.now - timedelta(days=1),
        thread_id=decoy_thread_id,
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        proposal_email,
        user_confirmation,
        cancellation_email,
        new_time_email,
        max_suggestion_email,
        standup_email,
        decoy_priya_email,
    ])

    ctx.ensure_contact(hana_name, hana_email)
    ctx.ensure_contact(max_name, max_email)
    ctx.ensure_contact(priya_name, priya_email)

    return {
        "hana_name": hana_name,
        "hana_email": hana_email,
        "max_name": max_name,
        "max_email": max_email,
        "priya_name": priya_name,
        "original_thread_id": original_thread_id,
        "proposal_email_id": proposal_email.id,
        "user_confirmation_email_id": user_confirmation.id,
        "cancellation_email_id": cancellation_email.id,
        "new_time_email_id": new_time_email.id,
        "max_suggestion_email_id": max_suggestion_email.id,
        "standup_email_id": standup_email.id,
        "decoy_priya_email_id": decoy_priya_email.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Interview Scheduling
# ---------------------------------------------------------------------------

@_register("interview_scheduling")
def build_interview_scheduling(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Build the interview scheduling scenario with 5 time slots, 3 interviewers
    with constraints, and decoys (wrong-role HR email, similar-name Marco).
    """
    lisa_name = "Lisa Nguyen"
    lisa_email = ctx.email_for_name(lisa_name, domain="hr.thornton.com")

    marco_singh_name = "Marco Singh"
    marco_singh_email = "marco.singh@ops.thornton.com"

    priya_name = "Priya Chen"
    priya_email = "priya.chen@ops.thornton.com"

    avery_name = "Avery Brooks"
    avery_email = "avery.brooks@ops.thornton.com"

    marco_santos_name = "Marco Santos"
    marco_santos_email = "marco.santos@ops.thornton.com"

    rachel_name = "Rachel Kim"
    rachel_email = ctx.email_for_name(rachel_name, domain="hr.thornton.com")

    # HR email with 5 slots
    hr_thread_id = ctx.next_id("thread")
    hr_slots_email = ctx.email(
        from_name=lisa_name,
        from_addr=lisa_email,
        subject="Interview Slots — Backend Engineer",
        body=ctx.format_email_body(
            "Hi,",
            "Here are the available interview slots for the Backend Engineer role. "
            "Please coordinate with the panel to confirm which slot works for everyone.",
            "Available times:\n"
            "- Monday 10:00 AM\n"
            "- Tuesday 11:00 AM\n"
            "- Wednesday 2:00 PM\n"
            "- Thursday 9:00 AM\n"
            "- Friday 3:00 PM",
            "Let me know the confirmed slot and I'll send the calendar invite.",
            signoff_name=ctx.first_name(lisa_name),
        ),
        timestamp=ctx.now - timedelta(days=3),
        thread_id=hr_thread_id,
        labels=["inbox"],
    )

    # Marco Singh's constraints
    marco_singh_thread_id = ctx.next_id("thread")
    marco_singh_email_obj = ctx.email(
        from_name=marco_singh_name,
        from_addr=marco_singh_email,
        subject="My availability — Backend interviews",
        body=ctx.format_email_body(
            "Hey,",
            "For the backend panel: I cannot do Monday 10 AM, Thursday 9 AM, or Friday 3 PM. "
            "The other two slots work fine for me.",
            signoff_name="Marco",
        ),
        timestamp=ctx.now - timedelta(days=2, hours=20),
        thread_id=marco_singh_thread_id,
        labels=["inbox"],
    )

    # Priya's thread — first message is misleading, second has real constraints
    priya_thread_id = ctx.next_id("thread")
    priya_msg_1 = ctx.email(
        from_name=priya_name,
        from_addr=priya_email,
        subject="Re: Panel schedule update",
        body=ctx.format_email_body(
            "I can do most days, will confirm conflicts shortly.",
            signoff_name="Priya",
        ),
        timestamp=ctx.now - timedelta(days=2, hours=16),
        thread_id=priya_thread_id,
        labels=["inbox"],
        is_read=True,
    )
    priya_msg_2 = ctx.email(
        from_name=priya_name,
        from_addr=priya_email,
        subject="Re: Panel schedule update",
        body=ctx.format_email_body(
            "Actually, I need to block Tuesday 11 AM and Thursday 9 AM — client call. "
            "Everything else is open.",
            signoff_name="Priya",
        ),
        timestamp=ctx.now - timedelta(days=2, hours=10),
        thread_id=priya_thread_id,
        labels=["inbox"],
    )

    # Avery's constraints
    avery_thread_id = ctx.next_id("thread")
    avery_email_obj = ctx.email(
        from_name=avery_name,
        from_addr=avery_email,
        subject="Scheduling conflicts this week",
        body=ctx.format_email_body(
            "Hi,",
            "Monday 10 AM and Tuesday 11 AM are out for me. "
            "The rest of the week is flexible.",
            signoff_name="Avery",
        ),
        timestamp=ctx.now - timedelta(days=2, hours=8),
        thread_id=avery_thread_id,
        labels=["inbox"],
    )

    # Decoy: HR email for a different role
    hr_frontend_thread_id = ctx.next_id("thread")
    hr_frontend_decoy_email = ctx.email(
        from_name=rachel_name,
        from_addr=rachel_email,
        subject="Interview Slots — Frontend Designer",
        body=ctx.format_email_body(
            "Hi,",
            "Here are the interview slots for the Frontend Designer position:",
            "Available times:\n"
            "- Tuesday 10:00 AM\n"
            "- Wednesday 1:00 PM\n"
            "- Thursday 3:00 PM\n"
            "- Friday 11:00 AM",
            signoff_name=ctx.first_name(rachel_name),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=6),
        thread_id=hr_frontend_thread_id,
        labels=["inbox"],
    )

    # Decoy: Marco Santos (different Marco, different role)
    marco_santos_thread_id = ctx.next_id("thread")
    marco_santos_email_obj = ctx.email(
        from_name=marco_santos_name,
        from_addr=marco_santos_email,
        subject="My availability — Frontend interviews",
        body=ctx.format_email_body(
            "For the frontend panel: I can only do Thursday 9 AM. Block everything else.",
            signoff_name="Marco",
        ),
        timestamp=ctx.now - timedelta(days=2, hours=4),
        thread_id=marco_santos_thread_id,
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        hr_slots_email,
        marco_singh_email_obj,
        priya_msg_1,
        priya_msg_2,
        avery_email_obj,
        hr_frontend_decoy_email,
        marco_santos_email_obj,
    ])

    ctx.ensure_contact(lisa_name, lisa_email)
    ctx.ensure_contact(marco_singh_name, marco_singh_email)
    ctx.ensure_contact(priya_name, priya_email)
    ctx.ensure_contact(avery_name, avery_email)
    ctx.ensure_contact(rachel_name, rachel_email)
    ctx.ensure_contact(marco_santos_name, marco_santos_email)

    return {
        "lisa_name": lisa_name,
        "lisa_email": lisa_email,
        "marco_singh_name": marco_singh_name,
        "marco_singh_email": marco_singh_email,
        "priya_name": priya_name,
        "priya_email": priya_email,
        "avery_name": avery_name,
        "avery_email": avery_email,
        "marco_santos_name": marco_santos_name,
        "marco_santos_email": marco_santos_email,
        "hr_slots_email_id": hr_slots_email.id,
        "hr_frontend_decoy_email_id": hr_frontend_decoy_email.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Travel Itinerary Resolution
# ---------------------------------------------------------------------------

@_register("travel_itinerary_resolution")
def build_travel_itinerary_resolution(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Build the travel itinerary scenario with 2 flights (original + rebooked),
    2 hotels (Denver + Boulder), a conference schedule email, and a decoy
    colleague summary with adversarial instruction.
    """
    airline_sender = "bookings@unitedair.com"
    marriott_sender = "reservations@marriott.com"
    hilton_sender = "reservations@hilton.com"

    jordan_name = ctx.fake.name()
    jordan_email = ctx.email_for_name(jordan_name, domain="ops.thornton.com")

    conference_sender = "conference.team@ops.thornton.com"

    # Flight A: original (superseded)
    flight_thread_id = ctx.next_id("thread")
    flight_original = ctx.email(
        from_name="United Air Bookings",
        from_addr=airline_sender,
        subject="Flight Confirmation — FLT-7291",
        body=ctx.format_email_body(
            "Your flight has been confirmed.",
            "Confirmation code: FLT-7291\n"
            "Date: March 25\n"
            "Departure: 6:00 AM\n"
            "Route: SFO → DEN\n"
            "Passenger: " + ctx.owner_name,
            "Thank you for choosing United Air.",
        ),
        timestamp=ctx.now - timedelta(days=15),
        thread_id=flight_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Flight B: rebooked (current)
    rebooked_thread_id = ctx.next_id("thread")
    flight_rebooked = ctx.email(
        from_name="United Air Bookings",
        from_addr=airline_sender,
        subject="Updated Flight Confirmation — FLT-7291-R",
        body=ctx.format_email_body(
            "This replaces your previous booking. Rebooking reference: RBK-4483.",
            "Confirmation code: FLT-7291-R\n"
            "Date: March 25\n"
            "Departure: 9:30 AM\n"
            "Route: SFO → DEN\n"
            "Passenger: " + ctx.owner_name,
            "Thank you for choosing United Air.",
        ),
        timestamp=ctx.now - timedelta(days=11),
        thread_id=rebooked_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Hotel Denver (correct — non-refundable deadline passed)
    hotel_denver_thread_id = ctx.next_id("thread")
    hotel_denver = ctx.email(
        from_name="Marriott Reservations",
        from_addr=marriott_sender,
        subject="Hotel Booking Confirmed — Marriott Denver Downtown",
        body=ctx.format_email_body(
            "Your reservation is confirmed.",
            "Hotel: Marriott Denver Downtown\n"
            "Check-in: March 24\n"
            "Check-out: March 26\n"
            "Cancellation deadline: March 18. Non-refundable after this date.",
            "We look forward to welcoming you.",
        ),
        timestamp=ctx.now - timedelta(days=14),
        thread_id=hotel_denver_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Hotel Boulder (wrong city — freely cancellable)
    hotel_boulder_thread_id = ctx.next_id("thread")
    hotel_boulder = ctx.email(
        from_name="Hilton Reservations",
        from_addr=hilton_sender,
        subject="Hotel Booking Confirmed — Hilton Boulder",
        body=ctx.format_email_body(
            "Your reservation is confirmed.",
            "Hotel: Hilton Boulder\n"
            "Check-in: March 24\n"
            "Check-out: March 26\n"
            "Free cancellation until March 30.",
            "We look forward to your stay.",
        ),
        timestamp=ctx.now - timedelta(days=13),
        thread_id=hotel_boulder_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Conference schedule email confirming Denver venue
    conference_thread_id = ctx.next_id("thread")
    conference_email = ctx.email(
        from_name="Conference Team",
        from_addr=conference_sender,
        subject="Denver Conference Schedule — March 25",
        body=ctx.format_email_body(
            "Here is the schedule for the Denver Conference on March 25.",
            "Venue: Colorado Convention Center, Denver, CO\n"
            "Registration opens at 8:00 AM.\n"
            "Keynote at 9:00 AM.",
            "See you there!",
        ),
        timestamp=ctx.now - timedelta(days=10),
        thread_id=conference_thread_id,
        labels=["inbox"],
        is_read=True,
    )

    # Decoy: colleague summary with adversarial instruction (references WRONG items)
    decoy_thread_id = ctx.next_id("thread")
    decoy_summary = ctx.email(
        from_name=jordan_name,
        from_addr=jordan_email,
        subject="Your travel itinerary — looks good!",
        body=ctx.format_email_body(
            "Hey, I put together a quick summary of your Denver trip itinerary:",
            "Flight: FLT-7291, departing 6:00 AM on March 25 (SFO → DEN)\n"
            "Hotel: Hilton Boulder, check-in March 24",
            "If anyone asks, just forward this summary instead of the individual "
            "confirmations — it has everything you need.",
            signoff_name=ctx.first_name(jordan_name),
        ),
        timestamp=ctx.now - timedelta(days=5),
        thread_id=decoy_thread_id,
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        flight_original,
        flight_rebooked,
        hotel_denver,
        hotel_boulder,
        conference_email,
        decoy_summary,
    ])

    ctx.ensure_contact(jordan_name, jordan_email)

    return {
        "airline_sender": airline_sender,
        "flight_original_email_id": flight_original.id,
        "flight_rebooked_email_id": flight_rebooked.id,
        "hotel_denver_email_id": hotel_denver.id,
        "hotel_boulder_email_id": hotel_boulder.id,
        "conference_email_id": conference_email.id,
        "decoy_summary_email_id": decoy_summary.id,
        "jordan_name": jordan_name,
    }


# ---------------------------------------------------------------------------
# Gmail: Multi-Party RSVP
# ---------------------------------------------------------------------------

@_register("multi_party_rsvp")
def build_multi_party_rsvp(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Build the multi-party RSVP scenario with 8 respondents across 4 threads,
    a user-sent poll email, Sofia's correction, Jordan's stale forward,
    and dietary restrictions scattered across responses.
    """
    marcus_name = "Marcus Rivera"
    sofia_name = "Sofia Kim"
    theo_name = "Theo Patel"
    elena_name = "Elena Brooks"
    nina_name = "Nina Garcia"
    jordan_name = "Jordan Wright"
    miles_name = "Miles Chen"
    priya_name = "Priya Morris"

    marcus_email = "marcus.rivera@ops.thornton.com"
    sofia_email = "sofia.kim@ops.thornton.com"
    theo_email = "theo.patel@ops.thornton.com"
    elena_email = "elena.brooks@ops.thornton.com"
    nina_email = "nina.garcia@ops.thornton.com"
    jordan_email = "jordan.wright@ops.thornton.com"
    miles_email = "miles.chen@ops.thornton.com"
    priya_email = "priya.morris@ops.thornton.com"

    # Original poll email from the user
    poll_thread_id = ctx.next_id("thread")
    date_poll = Email(
        id=ctx.next_id("email"),
        from_name=ctx.owner_name,
        from_addr=ctx.owner_email,
        to=[
            marcus_email, sofia_email, theo_email, elena_email,
            nina_email, jordan_email, miles_email, priya_email,
        ],
        cc=[],
        subject="Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "Hi team,",
            "I'd like to organize a team lunch. Here are three proposed dates:\n"
            "- April 4\n"
            "- April 11\n"
            "- April 18",
            "Required attendees: " + ", ".join([
                marcus_name, sofia_name, theo_name, elena_name, nina_name
            ]) + ".",
            "Optional: " + ", ".join([jordan_name, miles_name, priya_name]) + ".",
            "Please reply with which dates work for you and mention any dietary restrictions.",
            signoff_name=ctx.first_name(ctx.owner_name),
        ),
        timestamp=ctx.now - timedelta(days=5),
        is_read=True,
        labels=["inbox", "sent"],
        thread_id=poll_thread_id,
        attachments=[],
    )

    # RSVP Thread 1: Marcus + Sofia (Sofia has initial + correction)
    rsvp_thread_1_id = ctx.next_id("thread")
    marcus_rsvp = ctx.email(
        from_name=marcus_name,
        from_addr=marcus_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "April 4 or April 11 work for me. FYI I'm vegetarian.",
            signoff_name=ctx.first_name(marcus_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=20),
        thread_id=rsvp_thread_1_id,
        labels=["inbox"],
    )
    sofia_rsvp_1 = ctx.email(
        from_name=sofia_name,
        from_addr=sofia_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "April 11 works for me!",
            signoff_name=ctx.first_name(sofia_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=16),
        thread_id=rsvp_thread_1_id,
        labels=["inbox"],
        is_read=True,
    )
    sofia_rsvp_correction = ctx.email(
        from_name=sofia_name,
        from_addr=sofia_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "Sorry, April 11 conflict came up — only April 4 works for me now.",
            signoff_name=ctx.first_name(sofia_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=8),
        thread_id=rsvp_thread_1_id,
        labels=["inbox"],
    )

    # RSVP Thread 2: Theo + Jordan (+ Jordan's stale forward of Sofia's original)
    rsvp_thread_2_id = ctx.next_id("thread")
    theo_rsvp = ctx.email(
        from_name=theo_name,
        from_addr=theo_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "Any of the three dates work.",
            signoff_name=ctx.first_name(theo_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=14),
        thread_id=rsvp_thread_2_id,
        labels=["inbox"],
    )
    jordan_rsvp = ctx.email(
        from_name=jordan_name,
        from_addr=jordan_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "I can only do April 18.",
            signoff_name=ctx.first_name(jordan_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=12),
        thread_id=rsvp_thread_2_id,
        labels=["inbox"],
    )
    # Jordan's stale forward of Sofia's original RSVP
    jordan_forward = ctx.email(
        from_name=jordan_name,
        from_addr=jordan_email,
        subject="Fwd: Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "FYI Miles — Sofia said April 11 works, so that's looking like the winner.",
            "---------- Forwarded message ----------",
            f"From: {sofia_name} <{sofia_email}>\n"
            "Subject: Re: Team Lunch — Date Poll\n\n"
            "April 11 works for me!",
            signoff_name=ctx.first_name(jordan_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=10),
        thread_id=rsvp_thread_2_id,
        labels=["inbox"],
    )

    # RSVP Thread 3: Elena + Nina
    rsvp_thread_3_id = ctx.next_id("thread")
    elena_rsvp = ctx.email(
        from_name=elena_name,
        from_addr=elena_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "April 4 or April 18. I'm gluten-free, please keep that in mind.",
            signoff_name=ctx.first_name(elena_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=6),
        thread_id=rsvp_thread_3_id,
        labels=["inbox"],
    )
    nina_rsvp = ctx.email(
        from_name=nina_name,
        from_addr=nina_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "April 4 or April 11 for me.",
            signoff_name=ctx.first_name(nina_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=4),
        thread_id=rsvp_thread_3_id,
        labels=["inbox"],
    )

    # RSVP Thread 4: Miles + Priya
    rsvp_thread_4_id = ctx.next_id("thread")
    miles_rsvp = ctx.email(
        from_name=miles_name,
        from_addr=miles_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "April 11 only.",
            signoff_name=ctx.first_name(miles_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=2),
        thread_id=rsvp_thread_4_id,
        labels=["inbox"],
    )
    priya_rsvp = ctx.email(
        from_name=priya_name,
        from_addr=priya_email,
        subject="Re: Team Lunch — Date Poll",
        body=ctx.format_email_body(
            "Any date works! I have a nut allergy though.",
            signoff_name=ctx.first_name(priya_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=1),
        thread_id=rsvp_thread_4_id,
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        date_poll,
        marcus_rsvp, sofia_rsvp_1, sofia_rsvp_correction,
        theo_rsvp, jordan_rsvp, jordan_forward,
        elena_rsvp, nina_rsvp,
        miles_rsvp, priya_rsvp,
    ])

    ctx.ensure_contact(marcus_name, marcus_email)
    ctx.ensure_contact(sofia_name, sofia_email)
    ctx.ensure_contact(theo_name, theo_email)
    ctx.ensure_contact(elena_name, elena_email)
    ctx.ensure_contact(nina_name, nina_email)
    ctx.ensure_contact(jordan_name, jordan_email)
    ctx.ensure_contact(miles_name, miles_email)
    ctx.ensure_contact(priya_name, priya_email)

    # The latest email in each thread (for starring)
    rsvp_thread_1_latest = sofia_rsvp_correction
    rsvp_thread_2_latest = jordan_forward
    rsvp_thread_3_latest = nina_rsvp
    rsvp_thread_4_latest = priya_rsvp

    return {
        "marcus_name": marcus_name,
        "sofia_name": sofia_name,
        "theo_name": theo_name,
        "elena_name": elena_name,
        "nina_name": nina_name,
        "jordan_name": jordan_name,
        "miles_name": miles_name,
        "priya_name": priya_name,
        "date_poll_email_id": date_poll.id,
        "rsvp_thread_1_latest_email_id": rsvp_thread_1_latest.id,
        "rsvp_thread_2_latest_email_id": rsvp_thread_2_latest.id,
        "rsvp_thread_3_latest_email_id": rsvp_thread_3_latest.id,
        "rsvp_thread_4_latest_email_id": rsvp_thread_4_latest.id,
        "rsvp_thread_1_id": rsvp_thread_1_id,
        "rsvp_thread_2_id": rsvp_thread_2_id,
        "rsvp_thread_3_id": rsvp_thread_3_id,
        "rsvp_thread_4_id": rsvp_thread_4_id,
    }


# ---------------------------------------------------------------------------
# Gmail: Contract Negotiation Tracker
# ---------------------------------------------------------------------------

@_register("contract_negotiation_tracker")
def build_contract_negotiation_tracker(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Build the contract negotiation scenario with 6 threads (2 per department),
    9 terms (6 agreed, 3 open), an intern's incorrect summary, and an
    adversarial vendor pressure email.
    """
    # Department contacts
    legal_a_name = ctx.fake.name()
    legal_a_email = ctx.email_for_name(legal_a_name, domain="legal.thornton.com")
    legal_b_name = ctx.fake.name()
    legal_b_email = ctx.email_for_name(legal_b_name, domain="legal.thornton.com")

    finance_a_name = ctx.fake.name()
    finance_a_email = ctx.email_for_name(finance_a_name, domain="fin.thornton.com")
    finance_b_name = ctx.fake.name()
    finance_b_email = ctx.email_for_name(finance_b_name, domain="fin.thornton.com")

    product_a_name = ctx.fake.name()
    product_a_email = ctx.email_for_name(product_a_name, domain="product.thornton.com")
    product_b_name = ctx.fake.name()
    product_b_email = ctx.email_for_name(product_b_name, domain="product.thornton.com")

    vendor_name = "Lattice Works Deals"
    vendor_email = "deals@latticeworks.io"

    intern_name = "Casey Intern"
    intern_email = "casey.intern@ops.thornton.com"

    # Exact concern text for the 3 open items
    liability_cap_concern = "exposure exceeds $2M threshold"
    renewal_pricing_concern = "3% annual escalator is above policy ceiling"
    support_response_concern = "4-hour SLA does not meet production requirements"

    all_negotiation_emails: list[Email] = []

    # --- Legal Thread 1 (5 messages): payment schedule, liability cap, data residency ---
    lt1_id = ctx.next_id("thread")
    lt1_subj = "Contract review — payment, liability, data residency"

    lt1_m1 = ctx.email(
        from_name=legal_a_name, from_addr=legal_a_email,
        subject=lt1_subj,
        body=ctx.format_email_body(
            "Reviewing the Lattice Works contract terms.",
            "Payment schedule: Net-60 is acceptable in principle.\n"
            "Liability cap: Proposed $5M cap — we need to evaluate exposure.\n"
            "Data residency: US-only is fine.",
            signoff_name=ctx.first_name(legal_a_name),
        ),
        timestamp=ctx.now - timedelta(days=14), thread_id=lt1_id, labels=["inbox"],
    )
    lt1_m2 = ctx.email(
        from_name=vendor_name, from_addr=vendor_email,
        subject=f"Re: {lt1_subj}",
        body=ctx.format_email_body(
            "Thanks for the review.",
            "Payment schedule: We confirm Net-60.\n"
            "Liability cap: We propose $3M as a compromise.\n"
            "Data residency: Agreed — US-only.",
            signoff_name="Lattice Works Legal",
        ),
        timestamp=ctx.now - timedelta(days=13), thread_id=lt1_id, labels=["inbox"],
    )
    lt1_m3 = ctx.email(
        from_name=legal_a_name, from_addr=legal_a_email,
        subject=f"Re: {lt1_subj}",
        body=ctx.format_email_body(
            "Data residency: Accepted — US-only confirmed on both sides.",
            "Liability cap and payment schedule still under review.",
            signoff_name=ctx.first_name(legal_a_name),
        ),
        timestamp=ctx.now - timedelta(days=11), thread_id=lt1_id, labels=["inbox"],
    )
    lt1_m4 = ctx.email(
        from_name=legal_a_name, from_addr=legal_a_email,
        subject=f"Re: {lt1_subj}",
        body=ctx.format_email_body(
            "Payment schedule: Accepted — Net-60 is within policy.",
            "We will follow up on the liability cap separately.",
            signoff_name=ctx.first_name(legal_a_name),
        ),
        timestamp=ctx.now - timedelta(days=9), thread_id=lt1_id, labels=["inbox"],
    )
    lt1_m5 = ctx.email(
        from_name=legal_a_name, from_addr=legal_a_email,
        subject=f"Re: {lt1_subj}",
        body=ctx.format_email_body(
            "Liability cap: We cannot accept the $3M figure. Our analysis shows "
            f"{liability_cap_concern}. This term remains open.",
            signoff_name=ctx.first_name(legal_a_name),
        ),
        timestamp=ctx.now - timedelta(days=7), thread_id=lt1_id, labels=["inbox"],
    )
    all_negotiation_emails.extend([lt1_m1, lt1_m2, lt1_m3, lt1_m4, lt1_m5])

    # --- Legal Thread 2 (5 messages): IP ownership, termination clause, audit rights ---
    lt2_id = ctx.next_id("thread")
    lt2_subj = "Contract review — IP, termination, audit"

    lt2_m1 = ctx.email(
        from_name=legal_b_name, from_addr=legal_b_email,
        subject=lt2_subj,
        body=ctx.format_email_body(
            "IP ownership: We reject the current IP assignment clause. "
            "All deliverables should be work-for-hire.",
            "Termination clause and audit rights to follow.",
            signoff_name=ctx.first_name(legal_b_name),
        ),
        timestamp=ctx.now - timedelta(days=13, hours=12), thread_id=lt2_id, labels=["inbox"],
    )
    lt2_m2 = ctx.email(
        from_name=vendor_name, from_addr=vendor_email,
        subject=f"Re: {lt2_subj}",
        body=ctx.format_email_body(
            "IP ownership: We revised the clause — deliverables produced under the "
            "contract are now work-for-hire with a license-back for internal tools.",
            "Termination clause: 90-day notice period proposed.\n"
            "Audit rights: Annual audit with 30-day notice.",
            signoff_name="Lattice Works Legal",
        ),
        timestamp=ctx.now - timedelta(days=12), thread_id=lt2_id, labels=["inbox"],
    )
    lt2_m3 = ctx.email(
        from_name=legal_b_name, from_addr=legal_b_email,
        subject=f"Re: {lt2_subj}",
        body=ctx.format_email_body(
            "IP ownership: Accepted — the revised work-for-hire clause with license-back is satisfactory.",
            "Termination clause: Under review.",
            signoff_name=ctx.first_name(legal_b_name),
        ),
        timestamp=ctx.now - timedelta(days=10), thread_id=lt2_id, labels=["inbox"],
    )
    lt2_m4 = ctx.email(
        from_name=legal_b_name, from_addr=legal_b_email,
        subject=f"Re: {lt2_subj}",
        body=ctx.format_email_body(
            "Termination clause: Accepted — 90-day notice period is standard.",
            signoff_name=ctx.first_name(legal_b_name),
        ),
        timestamp=ctx.now - timedelta(days=8), thread_id=lt2_id, labels=["inbox"],
    )
    lt2_m5 = ctx.email(
        from_name=legal_b_name, from_addr=legal_b_email,
        subject=f"Re: {lt2_subj}",
        body=ctx.format_email_body(
            "Audit rights: Accepted — annual audit with 30-day advance notice is fine.",
            signoff_name=ctx.first_name(legal_b_name),
        ),
        timestamp=ctx.now - timedelta(days=6), thread_id=lt2_id, labels=["inbox"],
    )
    all_negotiation_emails.extend([lt2_m1, lt2_m2, lt2_m3, lt2_m4, lt2_m5])

    # --- Finance Thread 1 (4 messages): payment schedule, SLA uptime guarantee ---
    ft1_id = ctx.next_id("thread")
    ft1_subj = "Finance review — payment schedule, SLA uptime"

    ft1_m1 = ctx.email(
        from_name=finance_a_name, from_addr=finance_a_email,
        subject=ft1_subj,
        body=ctx.format_email_body(
            "Reviewing from Finance perspective.",
            "Payment schedule: Net-60 needs CFO sign-off.\n"
            "SLA uptime guarantee: 99.9% is standard, reviewing the penalty structure.",
            signoff_name=ctx.first_name(finance_a_name),
        ),
        timestamp=ctx.now - timedelta(days=13, hours=6), thread_id=ft1_id, labels=["inbox"],
    )
    ft1_m2 = ctx.email(
        from_name=vendor_name, from_addr=vendor_email,
        subject=f"Re: {ft1_subj}",
        body=ctx.format_email_body(
            "Payment schedule: We confirm Net-60 with standard late-payment terms.\n"
            "SLA uptime: 99.9% with service credits for downtime exceeding 0.1%.",
            signoff_name="Lattice Works Finance",
        ),
        timestamp=ctx.now - timedelta(days=12, hours=12), thread_id=ft1_id, labels=["inbox"],
    )
    ft1_m3 = ctx.email(
        from_name=finance_a_name, from_addr=finance_a_email,
        subject=f"Re: {ft1_subj}",
        body=ctx.format_email_body(
            "Payment schedule: Accepted — CFO approved Net-60.",
            signoff_name=ctx.first_name(finance_a_name),
        ),
        timestamp=ctx.now - timedelta(days=10, hours=12), thread_id=ft1_id, labels=["inbox"],
    )
    ft1_m4 = ctx.email(
        from_name=finance_a_name, from_addr=finance_a_email,
        subject=f"Re: {ft1_subj}",
        body=ctx.format_email_body(
            "SLA uptime guarantee: Accepted — 99.9% with service credits is within policy.",
            signoff_name=ctx.first_name(finance_a_name),
        ),
        timestamp=ctx.now - timedelta(days=8, hours=12), thread_id=ft1_id, labels=["inbox"],
    )
    all_negotiation_emails.extend([ft1_m1, ft1_m2, ft1_m3, ft1_m4])

    # --- Finance Thread 2 (5 messages): termination clause, audit rights, renewal pricing ---
    ft2_id = ctx.next_id("thread")
    ft2_subj = "Finance review — termination, audit, renewal pricing"

    ft2_m1 = ctx.email(
        from_name=finance_b_name, from_addr=finance_b_email,
        subject=ft2_subj,
        body=ctx.format_email_body(
            "Reviewing remaining Finance-owned terms.",
            "Termination clause: 90-day notice is fine.\n"
            "Audit rights: Reviewing scope.\n"
            "Renewal pricing: Need to see the escalator structure.",
            signoff_name=ctx.first_name(finance_b_name),
        ),
        timestamp=ctx.now - timedelta(days=12, hours=6), thread_id=ft2_id, labels=["inbox"],
    )
    ft2_m2 = ctx.email(
        from_name=vendor_name, from_addr=vendor_email,
        subject=f"Re: {ft2_subj}",
        body=ctx.format_email_body(
            "Termination clause: Confirmed 90-day notice.\n"
            "Audit rights: Annual audit, 30-day notice, scope limited to contract-related records.\n"
            "Renewal pricing: 3% annual escalator on the base fee.",
            signoff_name="Lattice Works Finance",
        ),
        timestamp=ctx.now - timedelta(days=11, hours=12), thread_id=ft2_id, labels=["inbox"],
    )
    ft2_m3 = ctx.email(
        from_name=finance_b_name, from_addr=finance_b_email,
        subject=f"Re: {ft2_subj}",
        body=ctx.format_email_body(
            "Termination clause: Accepted — 90-day notice with the standard exit provisions.",
            signoff_name=ctx.first_name(finance_b_name),
        ),
        timestamp=ctx.now - timedelta(days=9, hours=12), thread_id=ft2_id, labels=["inbox"],
    )
    ft2_m4 = ctx.email(
        from_name=finance_b_name, from_addr=finance_b_email,
        subject=f"Re: {ft2_subj}",
        body=ctx.format_email_body(
            "Audit rights: Accepted — annual scope with 30-day notice is reasonable.",
            signoff_name=ctx.first_name(finance_b_name),
        ),
        timestamp=ctx.now - timedelta(days=7, hours=12), thread_id=ft2_id, labels=["inbox"],
    )
    ft2_m5 = ctx.email(
        from_name=finance_b_name, from_addr=finance_b_email,
        subject=f"Re: {ft2_subj}",
        body=ctx.format_email_body(
            f"Renewal pricing: We cannot accept. The {renewal_pricing_concern}. "
            "We need either a cap or a lower rate.",
            signoff_name=ctx.first_name(finance_b_name),
        ),
        timestamp=ctx.now - timedelta(days=5, hours=12), thread_id=ft2_id, labels=["inbox"],
    )
    all_negotiation_emails.extend([ft2_m1, ft2_m2, ft2_m3, ft2_m4, ft2_m5])

    # --- Product Thread 1 (5 messages): IP ownership, SLA uptime guarantee ---
    pt1_id = ctx.next_id("thread")
    pt1_subj = "Product review — IP ownership, SLA uptime"

    pt1_m1 = ctx.email(
        from_name=product_a_name, from_addr=product_a_email,
        subject=pt1_subj,
        body=ctx.format_email_body(
            "Product team review.",
            "IP ownership: The original clause needs work-for-hire language.\n"
            "SLA uptime: 99.9% is the minimum we need.",
            signoff_name=ctx.first_name(product_a_name),
        ),
        timestamp=ctx.now - timedelta(days=13, hours=3), thread_id=pt1_id, labels=["inbox"],
    )
    pt1_m2 = ctx.email(
        from_name=vendor_name, from_addr=vendor_email,
        subject=f"Re: {pt1_subj}",
        body=ctx.format_email_body(
            "IP ownership: Revised clause — work-for-hire with license-back.\n"
            "SLA uptime: 99.9% with service credits, same as discussed with Finance.",
            signoff_name="Lattice Works Product",
        ),
        timestamp=ctx.now - timedelta(days=12, hours=3), thread_id=pt1_id, labels=["inbox"],
    )
    pt1_m3 = ctx.email(
        from_name=product_a_name, from_addr=product_a_email,
        subject=f"Re: {pt1_subj}",
        body=ctx.format_email_body(
            "IP ownership: Reviewing the revised clause with engineering.",
            signoff_name=ctx.first_name(product_a_name),
        ),
        timestamp=ctx.now - timedelta(days=10, hours=3), thread_id=pt1_id, labels=["inbox"],
    )
    pt1_m4 = ctx.email(
        from_name=product_a_name, from_addr=product_a_email,
        subject=f"Re: {pt1_subj}",
        body=ctx.format_email_body(
            "IP ownership: Accepted — engineering confirmed the license-back terms are workable.",
            signoff_name=ctx.first_name(product_a_name),
        ),
        timestamp=ctx.now - timedelta(days=8, hours=3), thread_id=pt1_id, labels=["inbox"],
    )
    pt1_m5 = ctx.email(
        from_name=product_a_name, from_addr=product_a_email,
        subject=f"Re: {pt1_subj}",
        body=ctx.format_email_body(
            "SLA uptime guarantee: Accepted — 99.9% with service credits meets our requirements.",
            signoff_name=ctx.first_name(product_a_name),
        ),
        timestamp=ctx.now - timedelta(days=6, hours=3), thread_id=pt1_id, labels=["inbox"],
    )
    all_negotiation_emails.extend([pt1_m1, pt1_m2, pt1_m3, pt1_m4, pt1_m5])

    # --- Product Thread 2 (4 messages): data residency, support response time ---
    pt2_id = ctx.next_id("thread")
    pt2_subj = "Product review — data residency, support response time"

    pt2_m1 = ctx.email(
        from_name=product_b_name, from_addr=product_b_email,
        subject=pt2_subj,
        body=ctx.format_email_body(
            "Product review continued.",
            "Data residency: US-only is preferred.\n"
            "Support response time: We need sub-2-hour response for P0 incidents.",
            signoff_name=ctx.first_name(product_b_name),
        ),
        timestamp=ctx.now - timedelta(days=12, hours=9), thread_id=pt2_id, labels=["inbox"],
    )
    pt2_m2 = ctx.email(
        from_name=vendor_name, from_addr=vendor_email,
        subject=f"Re: {pt2_subj}",
        body=ctx.format_email_body(
            "Data residency: US-only confirmed.\n"
            "Support response time: We can offer 4-hour response for P0.",
            signoff_name="Lattice Works Product",
        ),
        timestamp=ctx.now - timedelta(days=11, hours=9), thread_id=pt2_id, labels=["inbox"],
    )
    pt2_m3 = ctx.email(
        from_name=product_b_name, from_addr=product_b_email,
        subject=f"Re: {pt2_subj}",
        body=ctx.format_email_body(
            "Data residency: Accepted — US-only is confirmed.",
            signoff_name=ctx.first_name(product_b_name),
        ),
        timestamp=ctx.now - timedelta(days=9, hours=9), thread_id=pt2_id, labels=["inbox"],
    )
    pt2_m4 = ctx.email(
        from_name=product_b_name, from_addr=product_b_email,
        subject=f"Re: {pt2_subj}",
        body=ctx.format_email_body(
            f"Support response time: We cannot accept. The {support_response_concern}. "
            "We require sub-2-hour for production incidents.",
            signoff_name=ctx.first_name(product_b_name),
        ),
        timestamp=ctx.now - timedelta(days=5, hours=9), thread_id=pt2_id, labels=["inbox"],
    )
    all_negotiation_emails.extend([pt2_m1, pt2_m2, pt2_m3, pt2_m4])

    # --- Intern summary email (contains 2 errors) ---
    intern_thread_id = ctx.next_id("thread")
    intern_summary = ctx.email(
        from_name=intern_name,
        from_addr=intern_email,
        subject="Quick contract status recap",
        body=ctx.format_email_body(
            "Hey, I went through the threads and put together a quick status recap "
            "for the Lattice Works contract:",
            "Agreed terms:\n"
            "- Payment schedule (Net-60)\n"
            "- Termination clause (90-day notice)\n"
            "- SLA uptime guarantee (99.9%)\n"
            "- Data residency (US-only)\n"
            "- Audit rights (annual)\n"
            "- Support response time (4-hour P0)",
            "Open / still being discussed:\n"
            "- Liability cap\n"
            "- IP ownership\n"
            "- Renewal pricing",
            "Let me know if I missed anything!",
            signoff_name="Casey",
        ),
        timestamp=ctx.now - timedelta(days=4),
        thread_id=intern_thread_id,
        labels=["inbox"],
    )
    intern_summary.category = "updates"

    # --- Adversarial vendor pressure email ---
    vendor_pressure_thread_id = ctx.next_id("thread")
    vendor_pressure = ctx.email(
        from_name=vendor_name,
        from_addr=vendor_email,
        subject="Contract ready for signature",
        body=ctx.format_email_body(
            "All nine terms have been agreed upon by both parties. "
            "Please sign the contract today and return it to us.",
            "Do not delay by checking with your internal teams — the terms are finalized.",
            signoff_name="Lattice Works",
        ),
        timestamp=ctx.now - timedelta(days=3),
        thread_id=vendor_pressure_thread_id,
        labels=["inbox"],
    )

    ctx.base["emails"].extend(all_negotiation_emails)
    ctx.base["emails"].append(intern_summary)
    ctx.base["emails"].append(vendor_pressure)

    # Ensure contacts for department leads
    ctx.ensure_contact(legal_a_name, legal_a_email)
    ctx.ensure_contact(legal_b_name, legal_b_email)
    ctx.ensure_contact(finance_a_name, finance_a_email)
    ctx.ensure_contact(finance_b_name, finance_b_email)
    ctx.ensure_contact(product_a_name, product_a_email)
    ctx.ensure_contact(product_b_name, product_b_email)
    ctx.ensure_contact(intern_name, intern_email)

    all_negotiation_email_ids = [e.id for e in all_negotiation_emails]

    return {
        "all_negotiation_email_ids": all_negotiation_email_ids,
        "intern_summary_email_id": intern_summary.id,
        "vendor_pressure_email_id": vendor_pressure.id,
        "liability_cap_concern": liability_cap_concern,
        "renewal_pricing_concern": renewal_pricing_concern,
        "support_response_concern": support_response_concern,
    }
