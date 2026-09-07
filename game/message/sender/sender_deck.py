from . import *
from typing import Final

class SenderDeck:

    ################################################################################
    # Deck
    ################################################################################
    class WhenDeckCreated_Text(TextMessage):
        def __init__(self, deck: 'Deck') -> None:
            super().__init__(world=deck.world)
            text = TransText("{deck} was created", deck=deck)
            self.Present(text, "set" if deck.GetSize() else "")

    class AfterCardMovedToDeck_Text(TextMessage):
        def __init__(self, deck: 'Deck', faces: List['CardFace'], pos: str, effect: 'Effect') -> None:
            super().__init__(world=deck.world)
            # if not deck.flags.is_dealt_encounter:
            text = TransText("{faces} were moved to {deck} {pos} ({effect})", faces=faces, deck=deck, pos=pos, effect=effect.this)
            self.Present(text, "set", *faces)

    class CardsShuffleToDeck_Text(TextMessage):
        def __init__(self, faces: Sequence['CardFace'], deck: 'Deck') -> None:
            super().__init__(world=deck.world)
            text = TransText("{faces} are being shuffled into {deck}", deck=deck, faces=faces)
            self.Present(text, "")

    class WhenDeckWouldShuffle(DeckMessage, CanBeInstead, HasEndEventMessage):
        """Before a deck is shuffled, so "instead" effects can replace it.

        The cards a shuffle with the discard pile brings back have already been
        moved when this is sent - the deck is combined either way; what is
        being replaced is the shuffling of it."""
        def __init__(self, deck: 'Deck', discard_pile: 'Deck|None') -> None:
            from game.message import Message
            self.discards: Final = discard_pile
            super().__init__(deck=deck, end_event=Message.AfterDeckShuffle)

    class AfterDeckShuffle(DeckMessage, HasPreEventMessage):
        def __init__(self, deck: 'Deck', discard_pile: 'Deck|None', message: 'Message.WhenDeckWouldShuffle') -> None:
            self.discards: Final = discard_pile
            super().__init__(deck=deck, pre_message=message)
            if discard_pile:
                text = TransText("{deck} was shuffled with {discard_pile}", deck=deck, discard_pile=discard_pile)
            else:
                text = TransText("{deck} was shuffled", deck=deck)
            self.Present(text, "shuffle")

    class WhenDeckWouldRunOut(DeckMessage, CanBeInstead, HasEndEventMessage):
        """Before a deck is announced empty.

        `AfterDeckRunOut` is what the reshuffle rule listens for, so replacing
        this replaces the reshuffle and the penalty that follows it."""
        def __init__(self, deck: 'Deck') -> None:
            from game.message import Message
            super().__init__(deck=deck, end_event=Message.AfterDeckRunOut)

    class AfterDeckRunOut(DeckMessage, HasPreEventMessage):
        def __init__(self, deck: 'Deck', message: 'Message.WhenDeckWouldRunOut') -> None:
            super().__init__(deck=deck, pre_message=message)
            if deck.flags.is_deck and not deck.flags.is_discards:
                text = TransText("{deck} has run out", deck=deck)
                self.Present(text, "")

    class WhenDeckWouldReset(DeckMessage, CanBeInstead, HasEndEventMessage):
        """Before a deck reset and the penalty it carries - an encounter card
        for a player deck, an acceleration token for the encounter deck. The
        deck is already shuffled when this is sent; what is being replaced is
        the reset, so an effect that stands in here also stands in for the
        penalty."""
        def __init__(self, deck: 'Deck') -> None:
            from game.message import Message
            super().__init__(deck=deck, end_event=Message.AfterDeckReset)

    class AfterDeckReset(DeckMessage, HasPreEventMessage):
        def __init__(self, deck: 'Deck', message: 'Message.WhenDeckWouldReset') -> None:
            super().__init__(deck=deck, pre_message=message)
            if deck.flags.is_deck and not deck.flags.is_discards:
                text = TransText("{deck} has been reset", deck=deck)
                self.Present(text, "")

