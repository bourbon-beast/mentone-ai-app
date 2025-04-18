import { useState } from "react";
import TeamList from "./TeamList";
import UpcomingGames from "./UpcomingGames";
import PlayerStats from "./PlayerStats";
import WeeklySummary from "./WeeklySummary";
import TeamPerformance from "./TeamPerformance";

const Dashboard = () => {
    const [activeTab, setActiveTab] = useState("upcoming");

    return (
        <div className="bg-gray-100 min-h-screen">
            {/* Header */}
            <header className="bg-blue-700 text-white shadow-md">
                <div className="container mx-auto py-4 px-6">
                    <div className="flex justify-between items-center">
                        <h1 className="text-2xl font-bold">Mentone Hockey Club Dashboard</h1>
                        <span className="text-sm">Season 2025</span>
                    </div>
                </div>
            </header>

            {/* Navigation Tabs */}
            <nav className="bg-white shadow-md">
                <div className="container mx-auto px-6">
                    <div className="flex space-x-4">
                        <button
                            onClick={() => setActiveTab("upcoming")}
                            className={`py-4 px-4 focus:outline-none ${
                                activeTab === "upcoming"
                                    ? "border-b-2 border-blue-600 text-blue-600 font-medium"
                                    : "text-gray-600 hover:text-blue-600"
                            }`}
                        >
                            Upcoming Games
                        </button>
                        <button
                            onClick={() => setActiveTab("teams")}
                            className={`py-4 px-4 focus:outline-none ${
                                activeTab === "teams"
                                    ? "border-b-2 border-blue-600 text-blue-600 font-medium"
                                    : "text-gray-600 hover:text-blue-600"
                            }`}
                        >
                            Teams
                        </button>
                        <button
                            onClick={() => setActiveTab("players")}
                            className={`py-4 px-4 focus:outline-none ${
                                activeTab === "players"
                                    ? "border-b-2 border-blue-600 text-blue-600 font-medium"
                                    : "text-gray-600 hover:text-blue-600"
                            }`}
                        >
                            Player Stats
                        </button>
                        <button
                            onClick={() => setActiveTab("summary")}
                            className={`py-4 px-4 focus:outline-none ${
                                activeTab === "summary"
                                    ? "border-b-2 border-blue-600 text-blue-600 font-medium"
                                    : "text-gray-600 hover:text-blue-600"
                            }`}
                        >
                            Weekly Summary
                        </button>
                        <button
                            onClick={() => setActiveTab("performance")}
                            className={`py-4 px-4 focus:outline-none ${
                                activeTab === "performance"
                                    ? "border-b-2 border-blue-600 text-blue-600 font-medium"
                                    : "text-gray-600 hover:text-blue-600"
                            }`}
                        >
                            Performance
                        </button>
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="container mx-auto py-6 px-6">
                <div className="bg-white rounded-lg shadow-md">
                    {activeTab === "upcoming" && <UpcomingGames />}
                    {activeTab === "teams" && <TeamList />}
                    {activeTab === "players" && <PlayerStats />}
                    {activeTab === "summary" && <WeeklySummary />}
                    {activeTab === "performance" && <TeamPerformance />}
                </div>
            </main>

            {/* Footer */}
            <footer className="bg-gray-800 text-gray-300 py-4">
                <div className="container mx-auto px-6 text-center text-sm">
                    <p>© 2025 Mentone Hockey Club. All data sourced from Hockey Victoria.</p>
                </div>
            </footer>
        </div>
    );
};

export default Dashboard;