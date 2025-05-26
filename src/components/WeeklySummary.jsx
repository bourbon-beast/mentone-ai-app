import { useState, useEffect } from "react";
import { collection, query, where, getDocs, orderBy } from "firebase/firestore";
import { db } from "../firebase";

const WeeklySummary = () => {
    const [summary, setSummary] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [games, setGames] = useState([]);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        const fetchRecentGames = async () => {
            try {
                setLoading(true);

                // Get games from the last 7 days
                const now = new Date();
                const lastWeek = new Date();
                lastWeek.setDate(now.getDate() - 7);

                const gamesQuery = query(
                    collection(db, "games"),
                    where("date", ">=", lastWeek),
                    where("date", "<=", now),
                    where("status", "==", "completed"),
                    orderBy("date", "desc")
                );

                const querySnapshot = await getDocs(gamesQuery);
                const gamesData = querySnapshot.docs.map(doc => ({
                    id: doc.id,
                    ...doc.data()
                }));

                setGames(gamesData);

                // Generate summary
                if (gamesData.length > 0) {
                    generateSummary(gamesData);
                } else {
                    setSummary("No completed games found in the past week.");
                }

                setLoading(false);
            } catch (err) {
                console.error("Error fetching recent games:", err);
                setError(err.message);
                setLoading(false);
            }
        };

        fetchRecentGames();
    }, []);

    const generateSummary = (gamesData) => {
        // Group games by type (Senior, Junior, Midweek)
        const gamesByType = gamesData.reduce((acc, game) => {
            const type = game.type || "Other";
            if (!acc[type]) {
                acc[type] = [];
            }
            acc[type].push(game);
            return acc;
        }, {});

        // Initialize summary
        let summaryText = `Weekly Mentone Hockey Club Results Summary - ${new Date().toLocaleDateString("en-AU", { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}\n\n`;

        // Add summary for each type
        Object.keys(gamesByType).forEach(type => {
            const typeGames = gamesByType[type];

            // Count wins, losses, draws
            const results = typeGames.reduce((acc, game) => {
                const homeIsMentone = game.home_team?.club === "Mentone";
                const awayIsMentone = game.away_team?.club === "Mentone";

                if (!homeIsMentone && !awayIsMentone) return acc;

                const homeScore = game.home_team?.score || 0;
                const awayScore = game.away_team?.score || 0;

                if (homeIsMentone) {
                    if (homeScore > awayScore) acc.wins++;
                    else if (homeScore < awayScore) acc.losses++;
                    else acc.draws++;
                } else {
                    if (awayScore > homeScore) acc.wins++;
                    else if (awayScore < homeScore) acc.losses++;
                    else acc.draws++;
                }

                return acc;
            }, { wins: 0, losses: 0, draws: 0 });

            // Add type header
            summaryText += `${type} Teams (${typeGames.length} games, ${results.wins}W ${results.losses}L ${results.draws}D)\n`;
            summaryText += "-".repeat(50) + "\n";

            // Add each game result
            typeGames.forEach(game => {
                const date = game.date?.toDate ? game.date.toDate() : new Date(game.date);
                const dateStr = date.toLocaleDateString("en-AU", { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });

                const homeTeam = game.home_team?.name || "Unknown";
                const awayTeam = game.away_team?.name || "Unknown";
                const homeScore = game.home_team?.score || 0;
                const awayScore = game.away_team?.score || 0;

                const homeIsMentone = game.home_team?.club === "Mentone";
                const awayIsMentone = game.away_team?.club === "Mentone";

                let result = "";
                if (homeIsMentone) {
                    if (homeScore > awayScore) result = "WIN";
                    else if (homeScore < awayScore) result = "LOSS";
                    else result = "DRAW";
                } else if (awayIsMentone) {
                    if (awayScore > homeScore) result = "WIN";
                    else if (awayScore < homeScore) result = "LOSS";
                    else result = "DRAW";
                }

                const teamToHighlight = homeIsMentone ? homeTeam : awayIsMentone ? awayTeam : null;
                const scoreDisplay = `${homeScore} : ${awayScore}`;

                summaryText += `${dateStr} - ${homeTeam} ${scoreDisplay} ${awayTeam} - ${result}\n`;
            });

            summaryText += "\n";
        });

        setSummary(summaryText);
    };

    const copyToClipboard = () => {
        navigator.clipboard.writeText(summary)
            .then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            })
            .catch(err => {
                console.error('Failed to copy: ', err);
            });
    };

    if (loading) {
        return <div className="text-center p-4">Generating weekly summary...</div>;
    }

    if (error) {
        return <div className="text-red-600 p-4">Error: {error}</div>;
    }

    return (
        <div className="p-4">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold text-blue-600">Weekly Summary</h2>
                <button
                    onClick={copyToClipboard}
                    className={`px-4 py-2 rounded-lg text-white ${copied ? "bg-green-600" : "bg-blue-600 hover:bg-blue-700"}`}
                >
                    {copied ? "Copied!" : "Copy to Clipboard"}
                </button>
            </div>

            {games.length === 0 ? (
                <div className="text-center p-4 bg-gray-100 rounded-lg">
                    No completed games found in the past week.
                </div>
            ) : (
                <div className="bg-white rounded-lg shadow-md p-4">
                    <pre className="whitespace-pre-wrap font-mono text-sm">{summary}</pre>
                </div>
            )}
        </div>
    );
};

export default WeeklySummary;