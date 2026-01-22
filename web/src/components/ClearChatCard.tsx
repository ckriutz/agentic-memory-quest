import { Button } from "@/components/ui/button"
import {
    Card,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"

interface ClearChatCardProps {
    onClearChat: () => void
}

export function ClearChatCard({ onClearChat }: ClearChatCardProps) {
    return (
        <Card className="w-full max-h-[150px]">
            <CardHeader className="text-center">
                <CardTitle>Chat History</CardTitle>
                <CardDescription>Clear all messages from the chat</CardDescription>
            </CardHeader>
            <CardFooter className="flex justify-center">
                <Button variant="destructive" onClick={onClearChat} className="cursor-pointer">
                    Clear Chat
                </Button>
            </CardFooter>
        </Card>
    )
}