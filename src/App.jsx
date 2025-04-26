// src/App.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout'; // Import the Layout
import UpcomingGames from './components/UpcomingGames';
import TeamList from './components/TeamList';
import TeamDetailPage from './components/TeamDetailPage'; // Import the new detail page
import TeamPerformance from './components/TeamPerformance';
import PlayerStats from './components/PlayerStats'; // Import placeholders if they exist
import WeeklySummary from './components/WeeklySummary'; // Import placeholders if they exist
import './App.css';

function App() {
    return (
        <BrowserRouter>
            <Routes>
                {/* Wrap all main routes in the Layout */}
                <Route path="/" element={<Layout />}>
                    {/* Index route for "/" (UpcomingGames) */}
                    <Route index element={<UpcomingGames />} />
                    {/* Route for the Teams List */}
                    <Route path="teams" element={<TeamList />} />
                    {/* Route for a specific Team Detail Page */}
                    <Route path="teams/:teamId" element={<TeamDetailPage />} />
                    {/* Route for Performance */}
                    <Route path="performance" element={<TeamPerformance />} />
                    {/* Route for Player Stats */}
                    <Route path="players" element={<PlayerStats />} />
                    {/* Route for Weekly Summary */}
                    <Route path="summary" element={<WeeklySummary />} />

                    {/* Optional: Add a 404 Not Found route */}
                    {/* <Route path="*" element={<NotFound />} /> */}
                </Route>
            </Routes>
        </BrowserRouter>
    );
}

export default App;