// src/components/MatchTimeline.tsx
import { Card } from "@/components/ui/card";
import { GoalIcon, RedCardIcon, YellowCardIcon, SubstitutionIcon, PenaltyIcon, RedYellowCardIcon } from "@/components/icons";
import type { MatchEvent, Team } from "@/types/match";
import { useEffect, useRef } from "react";
import type { FC } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface MatchTimelineProps {
    homeTeam: Team;
    awayTeam: Team;
    finalScore: string;
    events: MatchEvent[];
}

const MatchTimeline: FC<MatchTimelineProps> = ({
    homeTeam,
    awayTeam,
    finalScore,
    events,
}) => {
    const timelineRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (timelineRef.current && events.length > 0) {
            timelineRef.current.scrollTo({
                top: timelineRef.current.scrollHeight,
                behavior: "smooth",
            });
        }
    }, [events]);

    return (
        <Card className="overflow-hidden w-full">
            {/* Match Header - Responsive layout */}
            <div className="flex items-center justify-center  mx-4 sm:mx-6 p-4 border-b gap-2 sm:gap-8">
                <TeamBadge team={homeTeam} isHome={true} />
                <div className="text-center min-w-[100px]">
                    <div className="text-xl sm:text-2xl md:text-4xl font-bold">{finalScore}</div>
                    <div className="text-xs text-muted-foreground">Final</div>
                </div>
                <TeamBadge team={awayTeam} isHome={false} />
            </div>

            {/* Timeline */}
            <div
                ref={timelineRef}
                className="relative max-h-[500px] overflow-y-auto overflow-x-hidden"
            >
                <div className="relative border-l border-muted mx-4 sm:mx-6 p-2 sm:p-4 space-y-3 sm:space-y-4">
                    <AnimatePresence>
                        {events.length === 0 ? (
                            <motion.p
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="text-center text-muted-foreground text-sm"
                            >
                                No events recorded
                            </motion.p>
                        ) : (
                            events.map((event, index) => (
                                <motion.div
                                    key={index}
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ duration: 0.3 }}
                                    className="relative"
                                >
                                    {"time" in event && event.type !== "half" && event.type !== "full" && (
                                        <span className="absolute -left-6 sm:-left-8 top-0 text-xs font-medium text-muted-foreground w-10 sm:w-12 text-center">
                                            {event.time}
                                        </span>
                                    )}

                                    {/* Goal Event */}
                                    {event.type === "goal" && (
                                        <div className="flex items-center gap-1 sm:gap-4">
                                            {/* Home team scorer */}
                                            <div className={`flex flex-1 min-w-0 justify-end ${event.team === "away" ? "opacity-50" : ""}`}>
                                                {event.team === "home" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<GoalIcon />}
                                                        iconAfter

                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>

                                            {/* Score */}
                                            <div className="flex items-center justify-center">
                                                {event.score && (
                                                    <span className="text-xs font-bold text-green-500 whitespace-nowrap">
                                                        {event.score}
                                                    </span>
                                                )}
                                            </div>

                                            {/* Away team scorer */}
                                            <div className={`flex flex-1 min-w-0 justify-start ${event.team === "home" ? "opacity-50" : ""}`}>
                                                {event.team === "away" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<GoalIcon />}
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {/* Yellow Card Event */}
                                    {event.type === "yellow_card" && (
                                        <div className="flex items-center gap-1 sm:gap-4">
                                            <div className={`flex flex-1 min-w-0 justify-end ${event.team === "away" ? "opacity-50" : ""}`}>
                                                {event.team === "home" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<YellowCardIcon />}
                                                        iconAfter

                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                            {/* Spacer */}
                                            <div className="flex items-center justify-center">
                                                <span className="text-xs font-bold opacity-0 whitespace-nowrap">0 - 0</span>
                                            </div>                                           <div className={`flex flex-1 min-w-0 justify-start ${event.team === "home" ? "opacity-50" : ""}`}>
                                                {event.team === "away" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<YellowCardIcon />}
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {/* Red Card Event */}
                                    {event.type === "red_card" && (
                                        <div className="flex items-center gap-1 sm:gap-4">
                                            <div className={`flex flex-1 min-w-0 justify-end ${event.team === "away" ? "opacity-50" : ""}`}>
                                                {event.team === "home" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<RedCardIcon />}
                                                        iconAfter
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                            {/* Spacer */}
                                            <div className="flex items-center justify-center">
                                                <span className="text-xs font-bold opacity-0 whitespace-nowrap">0 - 0</span>
                                            </div>
                                            <div className={`flex flex-1 min-w-0 justify-start ${event.team === "home" ? "opacity-50" : ""}`}>
                                                {event.team === "away" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<RedCardIcon />}
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {/* Yellow-Red (second yellow leading to red) */}
                                    {event.type === "yellow_red" && (
                                        <div className="flex items-center gap-1 sm:gap-4">
                                            <div className={`flex flex-1 min-w-0 justify-end ${event.team === "away" ? "opacity-50" : ""}`}>
                                                {event.team === "home" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<RedYellowCardIcon />}
                                                        iconAfter

                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                            {/* Spacer */}
                                            <div className="flex items-center justify-center">
                                                <span className="text-xs font-bold opacity-0 whitespace-nowrap">0 - 0</span>
                                            </div>                                           <div className={`flex flex-1 min-w-0 justify-start ${event.team === "home" ? "opacity-50" : ""}`}>
                                                {event.team === "away" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<RedYellowCardIcon />}
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {/* Penalty Event */}
                                    {event.type === "penalty" && (
                                        <div className="flex items-center gap-1 sm:gap-4">
                                            <div className={`flex flex-1 min-w-0 justify-end ${event.team === "away" ? "opacity-50" : ""}`}>
                                                {event.team === "home" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<PenaltyIcon />}
                                                        iconAfter
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                            <div className="flex items-center justify-center">
                                                {event.score && (
                                                    <span className="text-xs font-bold text-green-500 whitespace-nowrap">
                                                        {event.score}
                                                    </span>
                                                )}
                                            </div>
                                            <div className={`flex flex-1 min-w-0 justify-start ${event.team === "home" ? "opacity-50" : ""}`}>
                                                {event.team === "away" && (
                                                    <PlayerBadge
                                                        player={event.player}
                                                        icon={<PenaltyIcon />}
                                                        className="text-xs sm:text-sm"
                                                    />
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {event.type === "substitution" && (
                                        <div className="flex items-center gap-1 sm:gap-4">
                                            {/* Home team substitution */}
                                            <div className={`flex flex-1 min-w-0 justify-end gap-2 ${event.team === "away" ? "opacity-50" : ""}`}>
                                                {event.team === "home" && (
                                                    <>
                                                        <PlayerBadge
                                                            player={event.player_out}
                                                            className="text-xs text-gray-500 line-through max-w-[100px] truncate"
                                                        />
                                                        <PlayerBadge
                                                            player={event.player_in}
                                                            className="text-xs sm:text-sm"
                                                            icon={<SubstitutionIcon />}
                                                            iconAfter
                                                        />
                                                    </>
                                                )}
                                            </div>

                                            {/* Spacer */}
                                            <div className="flex items-center justify-center">
                                                <span className="text-xs font-bold opacity-0 whitespace-nowrap">0 - 0</span>
                                            </div>

                                            {/* Away team substitution */}
                                            <div className={`flex flex-1 min-w-0 justify-start gap-2 ${event.team === "home" ? "opacity-50" : ""}`}>
                                                {event.team === "away" && (
                                                    <>
                                                        <PlayerBadge
                                                            player={event.player_in}
                                                            className="text-xs sm:text-sm"
                                                            icon={<SubstitutionIcon />}
                                                        />
                                                        <PlayerBadge
                                                            player={event.player_out}
                                                            className="text-xs text-gray-500 line-through max-w-[100px] truncate"
                                                        />
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    )}



                                    {/* Half Time / Full Time */}
                                    {(event.type === "half" || event.type === "full") && (
                                        <div className="flex items-center justify-between ml-2 py-1 px-2 sm:px-3 text-xs sm:text-sm text-muted-foreground bg-muted rounded-md">
                                            <span>{event.label}</span>
                                            <span className="font-bold ml-2">{event.score}</span>
                                        </div>
                                    )}
                                </motion.div>
                            ))
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </Card>
    );
};

// Team badge with responsive sizing
const TeamBadge: React.FC<{ team: Team; isHome: boolean }> = ({ team }) => (
    <div className="flex flex-col items-center gap-1">
        {team.logo ? (
            <img
                src={team.logo}
                alt={team.name}
                className="w-8 h-8 sm:w-12 sm:h-12 md:w-14 md:h-14 object-contain"
            />
        ) : (
            <span className="text-lg sm:text-xl font-bold">{team.name.charAt(0)}</span>
        )}
        <span className="text-lg text-muted-foreground truncate text-center w-full">
            {team.name}
        </span>
    </div>
);


// Player badge with responsive text and optional icon placement
const PlayerBadge: React.FC<{
    player?: string | null;
    icon?: React.ReactNode;
    iconAfter?: boolean;
    className?: string;
}> = ({
    player,
    icon,
    iconAfter,
    className = ""
}) => (
        <div className={`flex items-center gap-2 min-w-0 ${className}`}>
            {!iconAfter && icon}
            <span className="truncate font-medium">{player || "Unknown Player"}</span>
            {iconAfter && icon}
        </div>
    );

export default MatchTimeline;