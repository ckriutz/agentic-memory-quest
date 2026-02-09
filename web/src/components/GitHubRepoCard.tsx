import { Github } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
    Card,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"

const REPO_URL = "https://github.com/ckriutz/agentic-memory-quest"

export function GitHubRepoCard() {
    return (
        <Card className="w-full max-h-[150px]">
            <CardHeader className="text-center">
                <CardTitle>GitHub Repository</CardTitle>
                <CardDescription>View the source code</CardDescription>
            </CardHeader>
            <CardFooter className="flex justify-center">
                <Button asChild variant="outline" className="cursor-pointer">
                    <a href={REPO_URL} target="_blank" rel="noreferrer">
                        <Github />
                        View on GitHub
                    </a>
                </Button>
            </CardFooter>
        </Card>
    )
}
