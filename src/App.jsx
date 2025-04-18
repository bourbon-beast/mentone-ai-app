import { useState } from 'react'
import './App.css'
import Navbar from './components/Navbar'
import TeamList from './components/TeamList'

function App() {
    return (
        <div className="min-h-screen bg-gray-100">
            <Navbar />
            <div className="container mx-auto px-4 py-8">
                <TeamList />
            </div>
            <footer className="bg-blue-900 text-white text-center py-4 mt-8">
                <p>© {new Date().getFullYear()} Mentone Hockey Club</p>
            </footer>
        </div>
    )
}

export default App