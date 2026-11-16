import { useState } from 'react';

const quotes = [
    { text: 'Wake up to reality! Nothing ever goes as planned in this accursed world.', char: 'Madara Uchiha', anime: 'Naruto' },
    { text: "If you don't take risks, you can't create a future.", char: 'Monkey D. Luffy', anime: 'One Piece' },
    { text: 'Push through the pain, giving up hurts more.', char: 'Vegeta', anime: 'Dragon Ball Z' },
    { text: 'A dropout will beat a genius through hard work.', char: 'Rock Lee', anime: 'Naruto' },
    { text: "It's not about whether I can. I have to do it.", char: 'Megumi Fushiguro', anime: 'Jujutsu Kaisen' },
    { text: 'Hard work is worthless for those that don’t believe in themselves.', char: 'Naruto Uzumaki', anime: 'Naruto' },
    { text: "Whatever you lose, you'll find it again. But what you throw away you'll never get back.", char: 'Kenshin Himura', anime: 'Rurouni Kenshin' },
    { text: 'Fear is not evil. It tells you what your weakness is.', char: 'Gildarts Clive', anime: 'Fairy Tail' },
    { text: "In this world, those who break the rules are scum, that's true, but those who abandon their friends are worse than scum.", char: 'Obito Uchiha', anime: 'Naruto' },
];

const AnimeQuote = () => {
    const [quote] = useState(() => quotes[Math.floor(Math.random() * quotes.length)]);

    return (
        <div className="border border-[#F2EFE9]/15 border-l-2 border-l-[#D95D24] bg-[#141414] px-6 py-5">
            <p className="font-serif text-base italic leading-relaxed tracking-wide text-[#F2EFE9]/90 md:text-lg">
                &ldquo;{quote.text}&rdquo;
            </p>
            <div className="mt-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em]">
                <span className="font-bold text-[#D95D24]">{quote.char}</span>
                <span className="text-[#9C968E]">/</span>
                <span className="text-[#9C968E]">{quote.anime}</span>
            </div>
        </div>
    );
};

export default AnimeQuote;
