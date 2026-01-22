import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"

interface UserCardProps {
    name?: string
    onLogin: (name: string) => void
    onLogout: () => void
}

export function UserCard({ name, onLogin, onLogout }: UserCardProps) {
    const [draftName, setDraftName] = useState("")

    useEffect(() => {
        if (name) {
            setDraftName("")
        }
    }, [name])

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (draftName.trim()) {
            onLogin(draftName)
        }
    }

    if (!name) {
        return (
            <Card className="w-full max-w-sm">
                <CardHeader>
                    <CardTitle>Connect to Chat</CardTitle>
                    <CardDescription>
                        Enter your name to enter the chat.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form id="login-form" onSubmit={handleSubmit}>
                        <div className="flex flex-col gap-6">
                            <div className="grid gap-2">
                                <Label htmlFor="name">Name</Label>
                                <Input
                                    id="name"
                                    type="text"
                                    placeholder="Your name"
                                    required
                                    value={draftName}
                                    onChange={(e) => setDraftName(e.target.value)}
                                />
                            </div>
                        </div>
                    </form>
                </CardContent>
                <CardFooter className="flex-col gap-2">
                    <Button type="submit" form="login-form" className="w-full cursor-pointer">
                        Login
                    </Button>
                </CardFooter>
            </Card>
        )
    }

    return (
        <Card className="w-full max-h-[150px]">
            <CardHeader className="text-center">
                <CardTitle>Welcome, {name}!</CardTitle>
                <CardDescription>Ask me about the weather!</CardDescription>
            </CardHeader>
            <CardFooter className="flex justify-center">
                <Button variant="outline" onClick={onLogout} className="cursor-pointer">
                    Logout
                </Button>
            </CardFooter>
        </Card>
    )
}