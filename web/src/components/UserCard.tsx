import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export function UserCard({ name, onLogout }: { name: string; onLogout: () => void }) {
    return (
        <Card className="w-full max-h-[150px]">
            <CardHeader className="text-center">
                <CardTitle>Welcome, {name}!</CardTitle>
                <CardDescription>Ask me about the weather!</CardDescription>
            </CardHeader>
            <CardFooter className="flex justify-center">
                <Button variant="outline" onClick={onLogout}>
                    Logout
                </Button>
            </CardFooter>
        </Card>
    )};